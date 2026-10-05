import importlib.util
from pathlib import Path

from rerank.fuzzy import load_fuzzy_classes

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bench", ROOT / "benchmark/run_bench.py")
bench = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bench)
FC = load_fuzzy_classes(ROOT / "assets/superpinyin.schema.yaml")


class FakeScorer:
    def __init__(self, gap=0.1):
        self.gap = gap

    def score_detail(self, _context, candidate):
        score = self.gap if candidate in {"风景很美", "今天天气"} else 0.0
        return score, 1


class FakeDecoder:
    def __init__(self, text="风景很美"):
        self.text = text

    def decode(self, _context, _syllables):
        return self.text


def test_percentile_and_empty_sample():
    assert bench.percentile([1, 2, 3, 4, 5], 0.95) == 5
    assert bench.percentile([], 0.5) == 0.0


def test_evaluation_measures_recall_l1_upgrade_and_validation():
    items = [{"keys": "fenjinghenmei", "expected": "风景很美", "context": "登高望远"}]
    baseline = {"fenjinghenmei": ["分静很没", "风景很美", "风景很每"]}
    metrics = bench.evaluate_items(items, baseline, FakeScorer(), FakeDecoder(), FC)
    assert metrics["total"] == 1
    assert metrics["recall20"] == 1 and metrics["baseline_first"] == 0
    assert metrics["l1_first"] == 1
    assert metrics["l2_triggered"] == 1 and metrics["l2_valid"] == 1
    assert metrics["l2_correct"] == 1


def test_non_han_l2_is_blocked_and_counted_as_t1_only_if_allowed():
    items = [{"keys": "jintian", "expected": "今天天气", "context": "前文"}]
    baseline = {"jintian": ["今天", "今天天气"]}
    metrics = bench.evaluate_items(items, baseline, FakeScorer(), FakeDecoder("今天3点"), FC)
    # Best differs from quick-path first and low confidence, so L2 is exercised.
    assert metrics["l2_triggered"] == 1
    assert metrics["l2_valid"] == 0 and metrics["l2_blocked"] == 1


def test_missing_candidates_are_counted_not_dropped():
    metrics = bench.evaluate_items(
        [{"keys": "jintian", "expected": "今天", "context": "上下文"}],
        {}, FakeScorer(), FakeDecoder(), FC,
    )
    assert metrics["total"] == 1 and metrics["recall20"] == 0
    assert metrics["details"][0]["note"] == "no-candidates"
