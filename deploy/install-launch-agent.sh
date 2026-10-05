#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This installer is for macOS launchd only." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${ROOT}/deploy/com.superinput.rerank.plist"
AGENTS="${HOME}/Library/LaunchAgents"
DEST="${AGENTS}/com.superinput.rerank.plist"
USER_ID="$(id -u)"
mkdir -p "${AGENTS}"

# plistlib performs XML escaping safely for paths containing spaces or special chars.
python3 - "${TEMPLATE}" "${DEST}" "${ROOT}" <<'PY'
import pathlib
import plistlib
import sys

template, destination, project_root = map(pathlib.Path, sys.argv[1:])
plist = plistlib.loads(template.read_bytes())
root = str(project_root)
plist["ProgramArguments"] = [part.replace("@@PROJECT_ROOT@@", root) for part in plist["ProgramArguments"]]
plist["WorkingDirectory"] = root
plist["EnvironmentVariables"]["PYTHONPATH"] = str(project_root / "src")
pathlib.Path(destination).write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=False))
PY
chmod 600 "${DEST}"
launchctl bootout "gui/${USER_ID}" "${DEST}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/${USER_ID}" "${DEST}"
launchctl kickstart -k "gui/${USER_ID}/com.superinput.rerank"
echo "Installed com.superinput.rerank from ${ROOT}"
