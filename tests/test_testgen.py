from pathlib import Path

import pytest

from rerank.fuzzy import load_fuzzy_classes
from rerank.testgen import SEEDS, build_dataset, make_keys, write_dataset

ROOT = Path(__file__).resolve().parents[1]
FC = load_fuzzy_classes(ROOT / "assets/superpinyin.schema.yaml")


def test_seed_set_has_context_and_sentence():
    assert len(SEEDS) >= 40
    assert all(len(context) >= 4 and len(sentence) >= 4 for context, sentence in SEEDS)


def test_known_fuzzy_swaps_and_clean_spelling():
    assert make_keys("风景很美", 1.0, FC) == "fenjinhengmei"
    assert make_keys("风景很美", 0.0, FC) == "fengjinghenmei"


def test_dataset_has_at_least_two_hundred_valid_cases():
    items = build_dataset(ROOT / "assets/superpinyin.schema.yaml")["items"]
    assert len(items) >= 200
    for item in items:
        assert item["keys"].isalpha() and len(item["keys"]) >= 4
        assert item["expected"] and item["context"]


def test_write_dataset_is_stable_and_creates_parent(tmp_path):
    destination = tmp_path / "nested" / "dataset.json"
    written = write_dataset(destination)
    assert written == destination and destination.exists()
    assert len(build_dataset()["items"]) == 200


def test_swap_ratio_is_validated():
    with pytest.raises(ValueError):
        make_keys("风景", 1.5, FC)
