from rerank.syllables import SYLLABLES, norm


def test_high_frequency_and_dictionary_syllables_are_present():
    for syllable in [
        "feng", "fen", "zhuang", "chuang", "lü", "nü", "er", "sheng",
        "jin", "xuan", "seng", "rua", "fan", "fang", "si", "tou", "zong",
        "long", "nong", "shuang", "qiong", "e", "en", "ei", "lo", "lia",
        "xiong", "jiong", "chui", "zhui", "shui", "dun", "gui", "kui", "hui",
    ]:
        assert syllable in SYLLABLES


def test_invalid_syllables_are_absent():
    for syllable in ["fengg", "ng", "vv", "zhx", "ian"]:
        assert syllable not in SYLLABLES


def test_norm_maps_v_to_umlaut_and_lowercases():
    assert norm("lv") == "lü"
    assert norm("nv3") == "nü3"
    assert norm("FENG") == "feng"
