"""Create a reproducible benchmark of clean and fuzzy-spelling examples."""

from __future__ import annotations

import json
from pathlib import Path

from .fuzzy import FuzzyClasses, load_fuzzy_classes
from .readings import char_readings
from .syllables import SYLLABLES

SEEDS: list[tuple[str, str]] = [
    ("周末的清晨很安静", "空气里有一点凉意"),
    ("朋友约我去逛超市", "我们分头买东西"),
    ("登高望远的心情", "风景美得让人屏住呼吸"),
    ("他是个很真诚的人", "说话从来不含糊"),
    ("公司楼下的银行", "每天早上都有人排队"),
    ("这座城市的生活节奏", "让人又爱又恨"),
    ("春天的森林里", "鸟叫声此起彼伏"),
    ("老人的心情很好", "每天坚持晨跑锻炼"),
    ("声音太大听不清", "请你重新说一遍"),
    ("真正的朋友", "不会在你落魄时沉默"),
    ("完成了今天的任务", "晚上可以安心休息"),
    ("深圳的春天很短", "一转眼就入夏了"),
    ("银杏叶黄了", "满地都是金色的"),
    ("生产力工具", "用好了能省一半时间"),
    ("找到证据了吗", "没有证据就不能下结论"),
    ("支持正版软件", "尊重开发者的劳动"),
    ("挑战自己的极限", "人生才有意思"),
    ("上传文件失败", "请检查网络连接"),
    ("车站出口在哪边", "我记得是在东边"),
    ("自然生长的果树", "果子味道更好"),
    ("智慧城市治理", "需要长期投入"),
    ("人民银行总部", "就在这条街上"),
    ("心情不好想吃火锅", "约上朋友一起"),
    ("拼命工作不是办法", "身体才是本钱"),
    ("亲自体验过的人", "才有发言权"),
    ("沉默是金", "但该说话时要说"),
    ("晨雾散去之后", "山下的城市清晰可见"),
    ("成功没有秘诀", "只有日复一日地坚持"),
    ("孩子的成长过程", "需要父母足够的耐心"),
    ("门前的花儿开了", "蝴蝶飞来飞去"),
    ("站在城市的高处", "看万家灯火"),
    ("商务谈判进行得很顺利", "双方都做了让步"),
    ("生产线出了故障", "工程师连夜抢修"),
    ("森林防火人人有责", "一点火星都不行"),
    ("证据链条完整", "案子可以移送了"),
    ("人生地不熟", "问问路边的老人"),
    ("城市治理的智慧", "藏在细节里"),
    ("声音识别技术", "这几年进步飞快"),
    ("认真的样子最帅", "你工作的时候真好看"),
    ("挣钱的速度", "赶不上房价的速度"),
]


def _swap(reading: str, fuzzy: FuzzyClasses) -> str | None:
    for syllable in sorted(SYLLABLES):
        if syllable != reading and fuzzy.match(syllable, reading):
            return syllable
    return None


def make_keys(sentence: str, swap_ratio: float, fuzzy: FuzzyClasses) -> str:
    if not 0.0 <= swap_ratio <= 1.0:
        raise ValueError("swap_ratio must be between 0 and 1")
    readings_by_position: list[tuple[int, str, str | None]] = []
    for index, char in enumerate(sentence):
        readings = char_readings(char)
        if readings:
            reading = readings[0]
            readings_by_position.append((index, reading, _swap(reading, fuzzy)))

    eligible = [entry for entry in readings_by_position if entry[2] is not None]
    swap_count = round(len(eligible) * swap_ratio)
    selected_positions = {entry[0] for entry in eligible[:swap_count]}
    by_position = {entry[0]: entry for entry in readings_by_position}
    out: list[str] = []
    for index, char in enumerate(sentence):
        entry = by_position.get(index)
        if entry is None:
            continue  # punctuation/space is not part of the raw pinyin string
        _, reading, swapped = entry
        out.append(swapped if index in selected_positions and swapped else reading)
    return "".join(out)


def build_dataset(schema_path: str | Path | None = None) -> dict:
    if schema_path is None:
        schema_path = Path(__file__).resolve().parents[2] / "assets/superpinyin.schema.yaml"
    fuzzy = load_fuzzy_classes(schema_path)
    items = []
    for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
        for context, sentence in SEEDS:
            items.append({
                "context": context,
                "keys": make_keys(sentence, ratio, fuzzy),
                "expected": sentence,
                "swap_ratio": ratio,
            })
    return {"items": items}


def write_dataset(out_path: str | Path | None = None) -> Path:
    if out_path is None:
        out_path = Path(__file__).resolve().parents[2] / "benchmark/datasets/dataset.json"
    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    print(f"dataset written: {write_dataset()}")
