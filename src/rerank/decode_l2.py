"""Local generative L2 decoder; generated text must pass validator first."""


def build_prompt(context: str, syllables: list[str]) -> str:
    return (
        "你是拼音转汉字引擎。根据给定拼音生成对应中文。"
        "只输出与拼音对应的中文，不要解释，不要添加未要求的内容。\n"
        f"前文：{context}\n"
        f"拼音：{' '.join(syllables)}\n"
        "输出："
    )


class LocalDecoder:
    def __init__(self, model_id: str):
        try:
            from mlx_lm import load
        except ImportError as exc:
            raise RuntimeError("MLX decoding requires Apple Silicon macOS and mlx-lm") from exc
        self.model, self.tokenizer = load(model_id)

    def decode(self, context: str, syllables: list[str]) -> str:
        from mlx_lm import generate

        result = generate(
            self.model,
            self.tokenizer,
            prompt=build_prompt(context, syllables),
            max_tokens=256,
            verbose=False,
        )
        return result.strip().splitlines()[0] if result.strip() else ""
