from pathlib import Path

from rerank.fuzzy import load_fuzzy_classes
from rerank.validator import min_edit_align, normalize_compare, normalize_text, validate

FC = load_fuzzy_classes(Path(__file__).resolve().parents[1] / "assets/superpinyin.schema.yaml")


def test_t0_exact_and_fuzzy_pass():
    exact = validate("今天天气很好", "jintiantianqihenhao", "T0", FC)
    fuzzy = validate("风景很美", "fenjinghenmei", "T0", FC)
    assert exact.ok and exact.edits == 0
    assert fuzzy.ok and fuzzy.edits == 0


def test_punctuation_is_ignored_for_alignment():
    result = validate("今天，天气很好！", "jintiantianqihenhao", "T0", FC)
    assert result.ok


def test_erhua_alignment_and_end_to_end():
    assert min_edit_align(["哪", "儿"], ["nar"], FC) == 0
    assert min_edit_align(["花", "儿"], ["huar"], FC) == 0
    verdict = validate("哪儿", "nar", "T0", FC)
    assert verdict.ok and verdict.edits == 0


def test_t1_allows_bounded_insertion_and_deletion():
    assert not validate("完成了任务", "wanchengrenwu", "T0", FC).ok
    insertion = validate("完成了任务", "wanchengrenwu", "T1", FC)
    assert insertion.ok and insertion.edits == 1
    deletion = validate("完成了务", "wanchenglerenwu", "T1", FC)
    assert deletion.ok and deletion.edits == 1


def test_t1_rejects_more_than_two_edits():
    verdict = validate("完成了的了任务", "wanchengrenwu", "T1", FC)
    assert not verdict.ok and verdict.reason == "limit"


def test_non_han_output_is_never_allowed_even_in_t1():
    for text in ("今天3点", "hello", "风景🙂很美"):
        assert not validate(text, "jintian", "T1", FC).ok


def test_unsegmentable_and_partial_trailing_fragment():
    invalid = validate("任意", "fff", "T0", FC)
    assert not invalid.ok and invalid.reason == "limit"
    # Only the complete prefix participates; `f` is an unfinished syllable.
    assert validate("今", "jinf", "T0", FC).ok


def test_punctuation_normalization():
    assert normalize_text("今天，天气好！") == normalize_text("今天 天气 好")
    assert normalize_compare("今天，天气好！", "今天天气好")
