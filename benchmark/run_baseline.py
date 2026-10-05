"""Run the compiled librime tool over unique benchmark keys."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _library_env() -> dict[str, str]:
    env = os.environ.copy()
    lib = str(ROOT / "third_party/install/lib")
    name = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    env[name] = lib + (os.pathsep + env[name] if env.get(name) else "")
    return env


def collect_baseline(dataset_path: pathlib.Path, tool: pathlib.Path) -> dict[str, list[str]]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    keys = list(dict.fromkeys(item["keys"] for item in dataset["items"]))
    payload = "".join(key + "\n" for key in keys)
    result = subprocess.run(
        [str(tool), str(ROOT / "baseline/data")],
        input=payload,
        capture_output=True,
        text=True,
        env=_library_env(),
        timeout=1800,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"librime baseline failed ({result.returncode}): {result.stderr[-2000:]}")
    candidates: dict[str, list[tuple[int, str]]] = {}
    for line in result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        key, raw_index, text = fields
        if raw_index.isdigit():
            candidates.setdefault(key, []).append((int(raw_index), text))
    output = {key: [text for _, text in sorted(rows)] for key, rows in candidates.items()}
    missing = set(keys) - output.keys()
    if missing:
        # Empty menus are meaningful and retained explicitly for recall accounting.
        output.update({key: [] for key in missing})
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, default=ROOT / "benchmark/datasets/dataset.json")
    parser.add_argument("--tool", type=pathlib.Path, default=ROOT / "baseline/dump_candidates")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "benchmark/datasets/baseline.json")
    args = parser.parse_args(argv)
    if not args.tool.is_file():
        parser.error(f"librime tool is missing: {args.tool}; build it with baseline/build.sh")
    baseline = collect_baseline(args.dataset, args.tool)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"baseline: {len(baseline)} keys -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
