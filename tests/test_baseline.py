import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "baseline" / "dump_candidates"
pytestmark = pytest.mark.integration


def _run(keys: str) -> list[str]:
    env = os.environ.copy()
    library_dir = ROOT / "third_party" / "install" / "lib"
    variable = "DYLD_LIBRARY_PATH" if os.uname().sysname == "Darwin" else "LD_LIBRARY_PATH"
    env[variable] = str(library_dir) + os.pathsep + env.get(variable, "")
    result = subprocess.run(
        [
            str(TOOL),
            str(ROOT / "third_party/install/share/rime-data"),
            str(ROOT / "baseline/data"),
        ],
        input=keys + "\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return [line.split("\t", 2)[2] for line in result.stdout.splitlines() if line.count("\t") == 2]


@pytest.mark.skipif(not TOOL.exists(), reason="librime baseline tool not built")
def test_top_candidate_contains_expected_context():
    candidates = _run("jintiantianqihenhao")
    assert candidates and any("今天" in candidate for candidate in candidates)


@pytest.mark.skipif(not TOOL.exists(), reason="librime baseline tool not built")
def test_fuzzy_schema_is_active():
    candidates = _run("fenjinghenmei")
    assert candidates and "风景很美" in candidates
