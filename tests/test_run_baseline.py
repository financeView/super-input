import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("run_baseline", ROOT / "benchmark/run_baseline.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_collect_baseline_deduplicates_keys_and_sorts_by_menu_index(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"items": [
        {"keys": "jintian"}, {"keys": "feng"}, {"keys": "jintian"},
    ]}), encoding="utf-8")
    tool = tmp_path / "fake-dump"
    tool.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "for key in sys.stdin:\n"
        " key=key.rstrip('\\n')\n"
        " print(f'{key}\\t1\\tsecond')\n"
        " print(f'{key}\\t0\\tfirst')\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    baseline = module.collect_baseline(dataset, tool)
    assert baseline == {"jintian": ["first", "second"], "feng": ["first", "second"]}


def test_system_library_path_is_platform_specific(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    linux_env = module._library_env()
    assert "third_party/install/lib" in linux_env["LD_LIBRARY_PATH"]
    assert "DYLD_LIBRARY_PATH" not in linux_env
