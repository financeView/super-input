"""Measure MLX mean-logprob scoring latency over model sizes and contexts."""

from __future__ import annotations

import argparse
import csv
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rerank.scorer import MLXScorer  # noqa: E402

MODELS = [
    "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "mlx-community/Qwen2.5-3B-Instruct-4bit",
]
CANDIDATE = "今天天气很好"


def run(output: pathlib.Path, repeats: int = 5) -> list[tuple[str, int, float]]:
    rows = []
    for model_id in MODELS:
        scorer = MLXScorer(model_id)
        for target_chars in (50, 100, 200):
            prefix = ("这是用于基准测试的前文。" * ((target_chars + 11) // 12))[:target_chars]
            samples = []
            for _ in range(repeats):
                started = time.perf_counter()
                scorer.score(prefix, CANDIDATE)
                samples.append((time.perf_counter() - started) * 1000)
            rows.append((model_id, target_chars, statistics.median(samples)))
            print(f"{model_id},{target_chars},{rows[-1][2]:.1f}ms")
        del scorer
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(("model", "prefix_chars", "median_ms"))
        writer.writerows((model, count, f"{latency:.1f}") for model, count, latency in rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, default=ROOT / "benchmark/latency.csv")
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args(argv)
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    run(args.output, args.repeats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
