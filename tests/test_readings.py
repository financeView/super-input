from pathlib import Path

from rerank.fuzzy import load_fuzzy_classes
from rerank.readings import char_readings, syllable_match

FC = load_fuzzy_classes(Path(__file__).resolve().parents[1] / "assets/superpinyin.schema.yaml")


def test_polyphonic_character_has_all_readings():
    readings = char_readings("行")
    assert "hang" in readings and "xing" in readings


def test_readings_are_toneless():
    assert "feng" in char_readings("风")


def test_non_han_returns_empty():
    assert char_readings("a") == []
    assert char_readings("，") == []
    assert char_readings("") == []


def test_fuzzy_match_works_in_both_directions():
    assert syllable_match("feng", "fen", FC)
    assert syllable_match("fen", "feng", FC)


def test_exact_and_mismatch():
    assert syllable_match("hao", "hao", FC)
    assert not syllable_match("fen", "hao", FC)
