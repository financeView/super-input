"""Local rerank HTTP service. IME-side stale/focus guards stay in Plan 2."""

from __future__ import annotations

import concurrent.futures
import hmac
import os
import pathlib
import secrets
import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .config import load_config

PROTOCOL_VERSION = "1"


def ensure_token(path: str | pathlib.Path) -> str:
    """Read/create a 256-bit token using restrictive permissions and atomic create."""
    token_path = pathlib.Path(path).expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(token_path, flags)
    except FileNotFoundError:
        value = secrets.token_urlsafe(32)
        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(token_path, create_flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(value + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return value
        except FileExistsError:
            return ensure_token(token_path)
    with os.fdopen(fd, "r", encoding="utf-8") as stream:
        if not os.path.isfile(token_path):
            raise ValueError("token path must be a regular file")
        os.fchmod(stream.fileno(), 0o600)
        token = stream.read().strip()
    if not token:
        raise ValueError("token file is empty")
    return token


class RerankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=1, max_length=128)
    request_id: int = Field(ge=0)
    keys: str = Field(max_length=512)
    preedit: str = Field(default="", max_length=2048)
    candidates: list[str] = Field(max_length=20)
    context: str = Field(default="", max_length=10000)
    trust: str = Field(default="T0", pattern="^(T0|T1)$")


def _merge_config(cfg: dict[str, Any] | None) -> dict[str, Any]:
    base = load_config()
    if cfg:
        cloud = dict(base.get("cloud", {}))
        cloud.update(cfg.get("cloud", {}))
        base.update(cfg)
        base["cloud"] = cloud
    schema = pathlib.Path(base["schema"]).expanduser()
    if not schema.is_absolute():
        schema = (pathlib.Path.cwd() / schema).resolve()
    base["schema"] = str(schema)
    if not 1 <= int(base["port"]) <= 65535:
        raise ValueError("port must be in 1..65535")
    if int(base["timeout_ms"]) < 1 or int(base["min_syllables"]) < 1:
        raise ValueError("timeout_ms and min_syllables must be positive")
    if float(base["l1_conf_threshold"]) < 0:
        raise ValueError("l1_conf_threshold cannot be negative")
    return base


def create_app(cfg: dict[str, Any] | None = None) -> FastAPI:
    config = _merge_config(cfg)
    from .fuzzy import load_fuzzy_classes
    from .policy import TimeoutWindow

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(lifespan=lifespan)
    app.state.cfg = config
    app.state.ready = False
    app.state.startup_error = None
    app.state.scorer = None
    app.state.decoder = None
    app.state.token = ensure_token(config["token_file"])
    app.state.fuzzy = load_fuzzy_classes(config["schema"])
    app.state.policy = TimeoutWindow()
    app.state.executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="super-input-inference"
    )

    def authenticate(authorization: str, protocol: str) -> None:
        expected = f"Bearer {app.state.token}"
        if not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="bad token")
        if protocol != PROTOCOL_VERSION:
            raise HTTPException(status_code=400, detail="protocol version mismatch")

    def fastpath(candidate_count: int) -> dict[str, Any]:
        return {
            "mode": "fastpath",
            "best": None,
            "confidence": 0.0,
            "order": list(range(candidate_count)),
            "l2_text": None,
        }

    @app.get("/health")
    def health(
        authorization: str = Header(""),
        protocol: str = Header("", alias="X-SuperInput-Protocol"),
    ) -> dict[str, Any]:
        authenticate(authorization, protocol)
        return {"ready": bool(app.state.ready), "protocol": PROTOCOL_VERSION}

    @app.post("/rerank")
    def rerank(
        request: RerankRequest,
        authorization: str = Header(""),
        protocol: str = Header("", alias="X-SuperInput-Protocol"),
    ) -> dict[str, Any]:
        authenticate(authorization, protocol)
        from .segment import segment_keys

        candidates = request.candidates[:20]
        syllables, _fragment = segment_keys(request.keys)
        if not syllables or len(syllables) < int(config["min_syllables"]) or not candidates:
            return fastpath(len(request.candidates))
        scorer = app.state.scorer
        if scorer is None:
            return fastpath(len(request.candidates))
        context_window = max(0, int(config["context_window"]))
        context = request.context[-context_window:] if context_window else ""
        deadline = time.monotonic() + int(config["timeout_ms"]) / 1000
        score_future = app.state.executor.submit(scorer.rank, context, candidates)
        try:
            order, best, confidence, _scores = score_future.result(
                timeout=max(0.0, deadline - time.monotonic())
            )
            if best is None or best < 0 or best >= len(candidates):
                return fastpath(len(request.candidates))
            order = [index for index in order if 0 <= index < len(candidates)]
            if not order:
                return fastpath(len(request.candidates))
        except concurrent.futures.TimeoutError:
            score_future.cancel()
            app.state.policy.record(request.session_id, True)
            return fastpath(len(request.candidates))
        except Exception:  # noqa: BLE001 — service degrades to the IME fast path
            return fastpath(len(request.candidates))

        mode, l2_text = "L1", None
        decoder = app.state.decoder
        if best != 0 and confidence < float(config["l1_conf_threshold"]) and decoder is not None:
            local_timed_out = False
            generated = ""
            cloud_cfg = config.get("cloud", {})
            if cloud_cfg.get("enabled") and app.state.policy.should_downgrade(request.session_id):
                try:
                    from .cloud import CloudDecoder, read_keychain_key

                    cloud_decoder = CloudDecoder(
                        cloud_cfg["base_url"], read_keychain_key(), cloud_cfg["model"],
                    )
                    future = app.state.executor.submit(cloud_decoder.decode, context, syllables)
                    generated = future.result(timeout=max(0.0, deadline - time.monotonic()))
                except concurrent.futures.TimeoutError:
                    # Cloud timeouts do not enter the *local* timeout window.
                    future.cancel()
                    app.state.policy.record(request.session_id, False)
                    return {
                        "mode": mode, "best": best, "confidence": confidence,
                        "order": order, "l2_text": None,
                    }
                except Exception:  # noqa: BLE001 — failed cloud L2 falls back locally
                    generated = ""

            if not generated:
                future = app.state.executor.submit(decoder.decode, context, syllables)
                try:
                    generated = future.result(timeout=max(0.0, deadline - time.monotonic()))
                except concurrent.futures.TimeoutError:
                    local_timed_out = True
                    future.cancel()
                    generated = ""
                except Exception:  # noqa: BLE001 — L2 failure falls back to L1
                    generated = ""
            app.state.policy.record(request.session_id, local_timed_out)
            if generated:
                from .validator import validate

                verdict = validate(generated, request.keys, request.trust, app.state.fuzzy)
                if verdict.ok:
                    mode, l2_text = "L2", generated

        return {
            "mode": mode,
            "best": best,
            "confidence": float(confidence),
            "order": order,
            "l2_text": l2_text,
        }

    def warmup() -> None:
        try:
            from .decode_l2 import LocalDecoder
            from .scorer import MLXScorer

            scorer = MLXScorer(config["model"])
            decoder = LocalDecoder(config["model"])
            scorer.score("预热前文。", "测试")
            app.state.scorer = scorer
            app.state.decoder = decoder
            app.state.ready = True
        except Exception as exc:  # keep the service alive in fastpath-only mode
            app.state.startup_error = type(exc).__name__
            app.state.ready = False

    if config.get("warmup"):
        threading.Thread(target=warmup, name="super-input-warmup", daemon=True).start()
    return app


def _create_prod_app() -> FastAPI:
    """Factory entry point for uvicorn/launchd; production explicitly warms up."""
    return create_app({**load_config(), "warmup": True})
