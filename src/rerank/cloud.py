"""OpenAI-compatible cloud decoder for BYOK L2 only."""

from __future__ import annotations

import subprocess
import time
from urllib.parse import urlparse

import requests

from .decode_l2 import build_prompt


class CloudError(RuntimeError):
    pass


def read_keychain_key() -> str:
    """Read the user-provided key from macOS Keychain; never logs its value."""
    try:
        process = subprocess.run(
            ["security", "find-generic-password", "-s", "superinput-rerank", "-w"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CloudError("macOS Keychain is unavailable") from exc
    if process.returncode != 0 or not process.stdout.strip():
        raise CloudError("keychain key not found for service superinput-rerank")
    return process.stdout.strip()


class CloudDecoder:
    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 10.0):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("cloud base_url must be an HTTPS URL")
        if not api_key or not model:
            raise ValueError("cloud API key and model are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def decode(self, context: str, syllables: list[str]) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是拼音转汉字引擎，只输出对应中文，不要解释。"},
                {"role": "user", "content": build_prompt(context, syllables)},
            ],
            "max_tokens": 256,
            "temperature": 0,
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for attempt in (0, 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_s,
                )
            except requests.RequestException as exc:
                if attempt:
                    raise CloudError("cloud network request failed") from exc
                time.sleep(0.5)
                continue
            if response.status_code == 200:
                try:
                    content = response.json()["choices"][0]["message"]["content"]
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    raise CloudError("malformed cloud response") from exc
                if not isinstance(content, str):
                    raise CloudError("cloud response content is not text")
                return content.strip()
            if response.status_code == 429 or response.status_code >= 500:
                if attempt:
                    raise CloudError(f"cloud upstream returned {response.status_code}")
                time.sleep(0.5 * (2**attempt))
                continue
            raise CloudError(f"cloud upstream returned {response.status_code}")
        raise CloudError("cloud request failed")
