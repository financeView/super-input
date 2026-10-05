import builtins

import pytest

from rerank.decode_l2 import LocalDecoder
from rerank.scorer import MLXScorer


def test_mlx_components_fail_with_actionable_message_without_importing_mlx(monkeypatch):
    original_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "mlx" or name.startswith("mlx.") or name == "mlx_lm":
            raise ImportError("not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(RuntimeError, match="Apple Silicon"):
        MLXScorer("unused")
    with pytest.raises(RuntimeError, match="Apple Silicon"):
        LocalDecoder("unused")
