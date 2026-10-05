from rerank.segment import all_segmentations, segment_keys


def test_plain_two_syllables():
    segmentations, fragment = all_segmentations("jintian")
    assert ["jin", "tian"] in segmentations and fragment == ""


def test_ambiguous_xian_keeps_both_parses():
    segmentations, fragment = all_segmentations("xian")
    assert ["xian"] in segmentations
    assert ["xi", "an"] in segmentations
    assert fragment == ""


def test_trailing_fragment_is_kept_for_next_round():
    segmentations, fragment = all_segmentations("jinf")
    assert segmentations == [["jin"]] and fragment == "f"


def test_long_input_has_full_parse():
    segmentations, fragment = all_segmentations("jintiantianqihenhao")
    assert fragment == "" and all(segmentations)


def test_v_normalizes_to_umlaut():
    segmentations, fragment = all_segmentations("lvdi")
    assert ["lü", "di"] in segmentations and fragment == ""


def test_erhua_syllable_is_segmentable():
    segmentations, fragment = all_segmentations("nar")
    assert ["nar"] in segmentations and fragment == ""


def test_convenience_segmenter_uses_deterministic_longest_parse():
    syllables, fragment = segment_keys("xian")
    assert syllables == ["xian"] and fragment == ""


def test_segmentation_limit_is_enforced():
    segmentations, _ = all_segmentations("xian", limit=1)
    assert len(segmentations) == 1
