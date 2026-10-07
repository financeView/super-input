"""Run the compiled librime tool over unique benchmark keys."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _library_env() -> dict[str, str]:
    env = os.environ.copy()
    lib = str(ROOT / "third_party/install/lib")
    name = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    env[name] = lib + (os.pathsep + env[name] if env.get(name) else "")
    return env


def collect_baseline(dataset_path: pathlib.Path, tool: pathlib.Path) -> tuple[dict[str, list[str]], int]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    keys = list(dict.fromkeys(item["keys"] for item in dataset["items"]))
    payload = "".join(key + "\n" for key in keys)
    result = subprocess.run(
        [
            str(tool),
            str(ROOT / "third_party/install/share/rime-data"),
            str(ROOT / "baseline/data"),
        ],
        input=payload,
        capture_output=True,
        text=True,
        env=_library_env(),
        timeout=1800,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"librime baseline failed ({result.returncode}): {result.stderr[-2000:]}")
    page_sizes = [int(value) for value in re.findall(r"(?m)^page_size=(\d+)\s*$", result.stderr)]
    if not page_sizes:
        raise RuntimeError(f"librime baseline did not report page_size: {result.stderr[-2000:]}")
    if len(set(page_sizes)) != 1:
        raise RuntimeError(f"librime baseline reported inconsistent page_size values: {page_sizes}")
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
    return output, page_sizes[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, default=ROOT / "benchmark/datasets/dataset.json")
    parser.add_argument("--tool", type=pathlib.Path, default=ROOT / "baseline/dump_candidates")
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "benchmark/datasets/baseline.json")
    args = parser.parse_args(argv)
    if not args.tool.is_file():
        parser.error(f"librime tool is missing: {args.tool}; build it with baseline/build.sh")
    baseline, page_size = collect_baseline(args.dataset, args.tool)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    metadata_path = args.output.with_name(f"{args.output.stem}.metadata.json")
    metadata_path.write_text(json.dumps({"page_size": page_size}, indent=2) + "\n", encoding="utf-8")
    print(f"baseline: {len(baseline)} keys (page_size={page_size}) -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
