"""Hard validation gate for generated L2 text (design spec §4.4)."""

from __future__ import annotations

import dataclasses
import unicodedata

from .fuzzy import FuzzyClasses, load_fuzzy_classes
from .readings import char_readings, syllable_match
from .segment import all_segmentations

PUNCT = frozenset("，。！？、；：“”‘’…—·,.!?;:'\"()（）-《》【】 ")
_DEFAULT_FC: FuzzyClasses | None = None


@dataclasses.dataclass(frozen=True)
class Verdict:
    ok: bool
    edits: int | None
    reason: str


def _fc(fuzzy: FuzzyClasses | None) -> FuzzyClasses:
    global _DEFAULT_FC
    if fuzzy is not None:
        return fuzzy
    if _DEFAULT_FC is None:
        from pathlib import Path

        schema = Path(__file__).resolve().parents[2] / "assets/superpinyin.schema.yaml"
        _DEFAULT_FC = load_fuzzy_classes(schema)
    return _DEFAULT_FC


def normalize_text(text: str) -> str:
    """Remove whitespace and the explicitly supported punctuation set."""
    return "".join(char for char in text if not char.isspace() and char not in PUNCT)


def normalize_compare(left: str, right: str) -> bool:
    return normalize_text(left) == normalize_text(right)


def _is_han(char: str) -> bool:
    category = unicodedata.category(char)
    cp = ord(char)
    return category.startswith("L") and (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2FA1F
        or 0x30000 <= cp <= 0x323AF
    )


def min_edit_align(chars: list[str], sylls: list[str], fuzzy: FuzzyClasses) -> int:
    """Minimum insertion/deletion cost; a valid erhua pair consumes one syllable."""
    m, n = len(chars), len(sylls)
    reads = [char_readings(char) for char in chars]
    inf = m + n + 1
    dp = [[inf] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0
    for i in range(m + 1):
        for j in range(n + 1):
            current = dp[i][j]
            if current >= inf:
                continue
            if i < m:
                dp[i + 1][j] = min(dp[i + 1][j], current + 1)
            if j < n:
                dp[i][j + 1] = min(dp[i][j + 1], current + 1)
            if i < m and j < n:
                if any(syllable_match(reading, sylls[j], fuzzy) for reading in reads[i]):
                    dp[i + 1][j + 1] = min(dp[i + 1][j + 1], current)
                if i + 1 < m and chars[i + 1] == "儿":
                    if any(syllable_match(reading + "r", sylls[j], fuzzy) for reading in reads[i]):
                        dp[i + 2][j + 1] = min(dp[i + 2][j + 1], current)
    return dp[m][n]


def validate(
    text: str,
    keys: str,
    trust: str = "T0",
    fuzzy: FuzzyClasses | None = None,
) -> Verdict:
    """Check every output Han character against an input syllable.

    T0 allows no unmatched characters/syllables. T1 permits at most two
    insertions/deletions, but never allows non-Han content other than the
    documented punctuation and whitespace.
    """
    if trust not in {"T0", "T1"}:
        return Verdict(False, None, "invalid-trust")
    if not isinstance(text, str) or not isinstance(keys, str):
        return Verdict(False, None, "invalid-input")
    if any(not (_is_han(char) or char.isspace() or char in PUNCT) for char in text):
        return Verdict(False, None, "disallowed-character")
    fc = _fc(fuzzy)
    segmentations, _fragment = all_segmentations(keys)
    if not segmentations:
        return Verdict(False, None, "unsegmentable")
    chars = [char for char in text if not char.isspace() and char not in PUNCT]
    best = min(min_edit_align(chars, syllables, fc) for syllables in segmentations)
    allowance = 0 if trust == "T0" else 2
    return Verdict(best <= allowance, best, "ok" if best <= allowance else "limit")
