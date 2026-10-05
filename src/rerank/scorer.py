"""L1 candidate likelihood ranking; MLX imports remain lazy."""

from __future__ import annotations

import math


def rank_from_scores(scores: list[float]) -> tuple[list[int], int | None, float]:
    """Return descending original indices, best original index and best/2nd gap."""
    if not scores:
        return [], None, 0.0
    order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
    best = order[0]
    best_score = scores[best]
    second_score = scores[order[1]] if len(order) > 1 else best_score
    confidence = max(0.0, best_score - second_score) if math.isfinite(best_score) else 0.0
    return order, best, confidence


class MLXScorer:
    """MLX-based mean logprob scorer. Construction is macOS Apple Silicon only."""

    def __init__(self, model_id: str):
        try:
            import mlx.core as mx
            from mlx_lm import load
        except ImportError as exc:
            raise RuntimeError("MLX scoring requires Apple Silicon macOS and mlx-lm") from exc
        self._mx = mx
        self.model, self.tokenizer = load(model_id)

    def score_detail(self, prefix: str, candidate: str) -> tuple[float, int]:
        """Return candidate logprob sum and token count under prefix context."""
        mx = self._mx
        prefix_ids = self.tokenizer.encode(prefix)
        full_ids = self.tokenizer.encode(prefix + candidate)
        # BPE may merge across the prefix/candidate boundary; those token(s)
        # cannot be scored conditional on exactly this prefix, so treat them as
        # candidate-side tokens from the first differing token position.
        common = 0
        while common < min(len(prefix_ids), len(full_ids)) and prefix_ids[common] == full_ids[common]:
            common += 1
        if common < len(prefix_ids):
            # Token boundary changed; re-encode a small prefix context fallback.
            common = min(len(prefix_ids), len(full_ids))
            while common and prefix_ids[:common] != full_ids[:common]:
                common -= 1
        count = len(full_ids) - common
        if count <= 0 or not full_ids:
            return float("-inf"), 0
        logits = self.model(mx.array(full_ids))
        logprobs = mx.log_softmax(logits.astype(mx.float32), axis=-1)
        total = 0.0
        for index in range(common, len(full_ids)):
            if index == 0:
                continue
            total += float(logprobs[index - 1, full_ids[index]])
        return total, count

    def score(self, prefix: str, candidate: str) -> float:
        total, count = self.score_detail(prefix, candidate)
        return total / count if count else float("-inf")

    def rank(self, prefix: str, candidates: list[str]):
        scores = [self.score(prefix, candidate) for candidate in candidates]
        order, best, confidence = rank_from_scores(scores)
        return order, best, confidence, scores


def probe_prefix_cache(model_id: str) -> bool | None:
    """Probe whether this installed mlx-lm exposes prompt-cache continuation.

    This is an actual hardware/model experiment and is unavailable off Apple
    Silicon. ``None`` means the optional MLX API is not installed.
    """
    try:
        import mlx.core as mx
        from mlx_lm import load
        from mlx_lm.models.cache import make_prompt_cache
    except ImportError:
        return None
    import time

    model, tokenizer = load(model_id)
    prefix_ids = tokenizer.encode("今天天气很好。" * 40)
    suffix_ids = tokenizer.encode("明天天气预报晴朗。")
    started = time.perf_counter()
    cold_logits = model(mx.array(prefix_ids + suffix_ids))
    mx.eval(cold_logits)
    cold_ms = time.perf_counter() - started
    cache = make_prompt_cache(model)
    prefix_logits = model(mx.array(prefix_ids), cache=cache)
    mx.eval(prefix_logits)
    started = time.perf_counter()
    warm_logits = model(mx.array(suffix_ids), cache=cache)
    mx.eval(warm_logits)
    warm_ms = time.perf_counter() - started
    consistent = bool(mx.allclose(cold_logits[:, -len(suffix_ids):, :], warm_logits, atol=1e-2))
    return bool(cold_ms > warm_ms * 1.5 and consistent)
