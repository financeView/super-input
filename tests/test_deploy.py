import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_launchd_template_is_valid_plist_with_required_placeholders():
    plist = plistlib.loads((ROOT / "deploy/com.superinput.rerank.plist").read_bytes())
    assert plist["Label"] == "com.superinput.rerank"
    assert plist["ProgramArguments"][0] == "@@PROJECT_ROOT@@/.venv/bin/uvicorn"
    assert "--factory" in plist["ProgramArguments"]
    assert plist["WorkingDirectory"] == "@@PROJECT_ROOT@@"


def test_deployment_shell_scripts_parse():
    for path in [ROOT / "deploy/install-launch-agent.sh", ROOT / "scripts/smoke.sh", ROOT / "baseline/build.sh"]:
        result = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
