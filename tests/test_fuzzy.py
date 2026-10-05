from pathlib import Path

import pytest

from rerank.fuzzy import load_fuzzy_classes

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "assets/superpinyin.schema.yaml"


@pytest.fixture(scope="module")
def fuzzy():
    return load_fuzzy_classes(SCHEMA)


def test_front_back_nasal_and_multiple_rule_membership(fuzzy):
    assert fuzzy.match("fen", "feng")
    assert fuzzy.match("jin", "jing")
    assert fuzzy.match("chen", "cheng")


def test_retroflex_equivalence(fuzzy):
    assert fuzzy.match("za", "zha")
    assert fuzzy.match("si", "shi")


def test_no_cross_rule_transitive_closure(fuzzy):
    assert fuzzy.match("zhan", "zan")
    assert fuzzy.match("zhan", "zhang")
    assert not fuzzy.match("zhan", "zang")


def test_unrelated_and_exact_unknown(fuzzy):
    assert not fuzzy.match("hao", "fen")
    assert fuzzy.match("not-a-syllable", "not-a-syllable")


def test_invalid_schema_fails_loudly(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("speller: {}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="speller/algebra"):
        load_fuzzy_classes(bad)
