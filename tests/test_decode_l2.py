from rerank.decode_l2 import build_prompt


def test_prompt_has_context_syllables_and_constrained_instruction():
    prompt = build_prompt("今天天气很好", ["fen", "jing", "hen", "mei"])
    assert "今天天气很好" in prompt
    assert "fen jing hen mei" in prompt
    assert "只输出" in prompt and "不要解释" in prompt
