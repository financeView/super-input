import importlib.util
import json
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
        " print(f'{key}\\t0\\tfirst')\n"
        "print('page_size=20', file=sys.stderr)\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    baseline, page_size = module.collect_baseline(dataset, tool)
    assert baseline == {"jintian": ["first", "second"], "feng": ["first", "second"]}
    assert page_size == 20


def test_main_writes_page_size_metadata_without_changing_baseline_shape(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"items": [{"keys": "jintian"}]}), encoding="utf-8")
    tool = tmp_path / "fake-dump"
    tool.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('page_size=20', file=sys.stderr)\n"
        "for key in sys.stdin:\n"
        " print(f'{key.rstrip()}\\t0\\ttoday')\n",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    output = tmp_path / "baseline.json"

    assert module.main(["--dataset", str(dataset), "--tool", str(tool), "--output", str(output)]) == 0

    assert json.loads(output.read_text(encoding="utf-8")) == {"jintian": ["today"]}
    metadata = tmp_path / "baseline.metadata.json"
    assert json.loads(metadata.read_text(encoding="utf-8")) == {"page_size": 20}


def test_collect_baseline_rejects_success_without_page_size(tmp_path):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(json.dumps({"items": [{"keys": "jintian"}]}), encoding="utf-8")
    tool = tmp_path / "fake-dump"
    tool.write_text("#!/usr/bin/env python3\nprint('jintian\\t0\\ttoday')\n", encoding="utf-8")
    tool.chmod(0o755)

    try:
        module.collect_baseline(dataset, tool)
    except RuntimeError as exc:
        assert "did not report page_size" in str(exc)
    else:
        raise AssertionError("missing page_size should not be silently accepted")


def test_system_library_path_is_platform_specific(monkeypatch):
    monkeypatch.setattr(module.sys, "platform", "linux")
    linux_env = module._library_env()
    assert "third_party/install/lib" in linux_env["LD_LIBRARY_PATH"]
    assert "DYLD_LIBRARY_PATH" not in linux_env
