"""Offline evaluation: recall ceiling, librime baseline, L1/L2, latency and KV.

Use ``python benchmark/run_bench.py [model-id]`` on Apple Silicon with MLX.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rerank.decode_l2 import LocalDecoder  # noqa: E402
from rerank.fuzzy import FuzzyClasses, load_fuzzy_classes  # noqa: E402
from rerank.scorer import MLXScorer, probe_prefix_cache, rank_from_scores  # noqa: E402
from rerank.segment import segment_keys  # noqa: E402
from rerank.validator import normalize_text, validate  # noqa: E402

CONF_THRESHOLD = 0.5
DEFAULT_MODEL = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"


def percentile(values: list[float], quantile: float) -> float:
    """Nearest-rank percentile; safe for empty samples."""
    if not values:
        return 0.0
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be in [0, 1]")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(quantile * len(ordered)) - 1)]


def evaluate_items(
    items: list[dict[str, Any]],
    baseline: dict[str, list[str]],
    scorer: Any,
    decoder: Any,
    fuzzy: FuzzyClasses,
    threshold: float = CONF_THRESHOLD,
) -> dict[str, Any]:
    """Evaluate using injectable implementations, enabling CPU-only tests."""
    metrics: dict[str, Any] = {
        "total": len(items), "recall20": 0, "baseline_first": 0,
        "l1_first": 0, "l1_sum_first": 0, "l2_triggered": 0,
        "l2_valid": 0, "l2_blocked": 0, "l2_wrong_valid": 0,
        "l2_correct": 0, "t1_extra_valid": 0,
        "l1_latency_ms": [], "l2_latency_ms": [], "confidences": [],
        "details": [],
    }
    for item in items:
        candidates = baseline.get(item["keys"], [])[:20]
        expected = normalize_text(item["expected"])
        if any(normalize_text(candidate) == expected for candidate in candidates):
            metrics["recall20"] += 1
        if candidates and normalize_text(candidates[0]) == expected:
            metrics["baseline_first"] += 1
        if not candidates:
            metrics["details"].append({**item, "note": "no-candidates"})
            continue

        started = time.perf_counter()
        sums: list[float] = []
        means: list[float] = []
        for candidate in candidates:
            total, token_count = scorer.score_detail(item["context"], candidate)
            sums.append(total)
            means.append(total / token_count if token_count > 0 else float("-inf"))
        order, best, confidence = rank_from_scores(means)
        metrics["l1_latency_ms"].append((time.perf_counter() - started) * 1000)
        metrics["confidences"].append(confidence)
        if best is None:
            metrics["details"].append({**item, "note": "no-scores"})
            continue
        if normalize_text(candidates[best]) == expected:
            metrics["l1_first"] += 1
        _, best_sum, _ = rank_from_scores(sums)
        if best_sum is not None and normalize_text(candidates[best_sum]) == expected:
            metrics["l1_sum_first"] += 1

        # Upgrade only when L1 differs from the fast-path first candidate and
        # its confidence gap is below the configured mean-logprob threshold.
        if best != 0 and confidence < threshold:
            metrics["l2_triggered"] += 1
            syllables, _fragment = segment_keys(item["keys"])
            started = time.perf_counter()
            try:
                generated = decoder.decode(item["context"], syllables or [])
            except Exception as exc:  # benchmark records a failed L2 attempt
                metrics["l2_blocked"] += 1
                metrics["l2_latency_ms"].append((time.perf_counter() - started) * 1000)
                metrics["details"].append({**item, "note": f"l2-error:{type(exc).__name__}"})
                continue
            metrics["l2_latency_ms"].append((time.perf_counter() - started) * 1000)
            verdict = validate(generated, item["keys"], "T0", fuzzy)
            if not verdict.ok:
                metrics["l2_blocked"] += 1
                if validate(generated, item["keys"], "T1", fuzzy).ok:
                    metrics["t1_extra_valid"] += 1
                metrics["details"].append({**item, "l2_text": generated, "l2_ok": False})
                continue
            metrics["l2_valid"] += 1
            if normalize_text(generated) == expected:
                metrics["l2_correct"] += 1
            else:
                metrics["l2_wrong_valid"] += 1
            metrics["details"].append({**item, "l2_text": generated, "l2_ok": True})
        else:
            metrics["details"].append({**item, "l1_best": candidates[best], "order": order})
    return metrics


def _pct(value: int, denominator: int) -> str:
    return f"{value / denominator:.1%}" if denominator else "n/a"


def render_report(
    model_id: str,
    metrics: dict[str, Any],
    kv_result: bool | None,
    page_size: int | None = None,
) -> str:
    total = metrics["total"]
    l1 = metrics["l1_latency_ms"]
    l2 = metrics["l2_latency_ms"]
    baseline_rate = metrics["baseline_first"] / total if total else 0.0
    l1_rate = metrics["l1_first"] / total if total else 0.0
    recall_rate = metrics["recall20"] / total if total else 0.0
    gain = l1_rate - baseline_rate
    recall_headroom_pp = (recall_rate - baseline_rate) * 100
    required_rate = baseline_rate + 0.15
    if not total:
        accuracy_gate = "NOT MEASURED"
    elif recall_rate < required_rate:
        accuracy_gate = (
            f"CALIBRATION REQUIRED: recall ceiling is {recall_headroom_pp:+.1f} pp above baseline, "
            f"below the uncalibrated +15.0 pp target ({required_rate:.1%}); "
            "calibrate against the measured ceiling per spec §7"
        )
    else:
        accuracy_gate = "PASS" if l1_rate >= required_rate else "FAIL"
    l1_p95 = percentile(l1, .95)
    latency_gate = "NOT MEASURED" if not l1 else ("PASS" if l1_p95 < 800 else "FAIL")
    kv_gate = "NOT RUN" if kv_result is None else ("SUPPORTED" if kv_result else "UNSUPPORTED")
    report = f"""# Offline benchmark report (Plan 1 gate)

- Model: `{model_id}`
- Dataset: {total} examples (40 seeds × 5 fuzzy-spelling ratios)
- **Top-20 recall ceiling**: {_pct(metrics['recall20'], total)}
- **librime baseline top-1 accuracy**: {_pct(metrics['baseline_first'], total)}
- **L1 top-1 accuracy (mean logprob)**: {_pct(metrics['l1_first'], total)}
- L1 gain over baseline: {gain:+.1%} (nominal target +15.0 percentage points; recall ceiling headroom {recall_headroom_pp:+.1f} pp)
- L1 top-1 accuracy (sum logprob comparison): {_pct(metrics['l1_sum_first'], total)}
- L1 confidence gap: p50={percentile(metrics['confidences'], .50):.3f}, p95={percentile(metrics['confidences'], .95):.3f}; threshold={CONF_THRESHOLD}
- L2 triggered: {metrics['l2_triggered']}; T0-valid: {metrics['l2_valid']}; blocked/failed: {metrics['l2_blocked']} (T1 additional pass: {metrics['t1_extra_valid']}); valid-but-wrong: {metrics['l2_wrong_valid']}; correct: {metrics['l2_correct']}
- L1 latency: p50={percentile(l1, .50):.0f}ms, p95={percentile(l1, .95):.0f}ms (target p95 <800ms, hard limit 1500ms)
- L2 latency: p50={percentile(l2, .50):.0f}ms, p95={percentile(l2, .95):.0f}ms across {len(l2)} attempted decodes (target p95 <2s)
- KV prefix cache probe: {kv_result}

## Gate decisions (human review required)

1. L1 gain ≥ +15 percentage points vs the same-schema librime baseline, interpreted against recall ceiling: **{accuracy_gate}**
2. L1 p95 <800ms: **{latency_gate}** (p95 {l1_p95:.0f}ms)
3. KV prefix-cache support: **{kv_gate}**
4. L2 validation rejection and hallucination proxy: **see metrics above; human review required**
5. RimeMenu page_size: **{page_size if page_size is not None else 'NOT CAPTURED'}** (measured from librime baseline); Squirrel commit callback text reading: **pending Plan 2 Task 1**
"""
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", nargs="?", default=DEFAULT_MODEL)
    parser.add_argument("--dataset", type=pathlib.Path, default=ROOT / "benchmark/datasets/dataset.json")
    parser.add_argument("--baseline", type=pathlib.Path, default=ROOT / "benchmark/datasets/baseline.json")
    parser.add_argument("--baseline-metadata", type=pathlib.Path)
    parser.add_argument("--skip-kv-probe", action="store_true", help="do not reload the model for KV-cache probe")
    args = parser.parse_args(argv)
    if not args.baseline.is_file():
        parser.error(f"missing {args.baseline}; run benchmark/run_baseline.py after building librime")
    items = json.loads(args.dataset.read_text(encoding="utf-8"))["items"]
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    metadata_path = args.baseline_metadata or args.baseline.with_name(f"{args.baseline.stem}.metadata.json")
    page_size = None
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        value = metadata.get("page_size")
        if isinstance(value, int) and not isinstance(value, bool):
            page_size = value
    fuzzy = load_fuzzy_classes(ROOT / "assets/superpinyin.schema.yaml")
    scorer = MLXScorer(args.model)
    decoder = LocalDecoder(args.model)
    metrics = evaluate_items(items, baseline, scorer, decoder, fuzzy)
    kv = None if args.skip_kv_probe else probe_prefix_cache(args.model)
    report = render_report(args.model, metrics, kv, page_size)
    out = ROOT / "benchmark/report.md"
    out.write_text(report, encoding="utf-8")
    (ROOT / "benchmark/results.json").write_text(
        json.dumps({**{k: v for k, v in metrics.items() if k != "details"}, "page_size": page_size}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
