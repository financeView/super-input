"""Dynamic-programming segmentation of raw pinyin keystrokes."""

from .syllables import SYLLABLES, norm

_MAX_SYLLABLE_LENGTH = 7  # zhuang + erhua r


def _valid_syllable(value: str) -> bool:
    return value in SYLLABLES or (value.endswith("r") and value[:-1] in SYLLABLES)


def _reachable(keys: str) -> list[bool]:
    reachable = [False] * (len(keys) + 1)
    reachable[0] = True
    for end in range(1, len(keys) + 1):
        for start in range(max(0, end - _MAX_SYLLABLE_LENGTH), end):
            if reachable[start] and _valid_syllable(keys[start:end]):
                reachable[end] = True
                break
    return reachable


def all_segmentations(keys: str, limit: int = 32) -> tuple[list[list[str]], str]:
    """Return segmentations of the longest complete-syllable prefix and tail.

    An incomplete trailing keystroke fragment is intentionally excluded from
    the syllable list and returned separately for the next debounce round.
    Longest syllables are enumerated first to make the convenience choice
    deterministic for ambiguous strings (e.g. ``xian``).
    """
    if limit < 1:
        raise ValueError("limit must be at least 1")
    normalized = norm(keys)
    cleaned = "".join(c for c in normalized if "a" <= c <= "z" or c == "ü")
    reachable = _reachable(cleaned)
    covered = max(index for index, ok in enumerate(reachable) if ok)
    results: list[list[str]] = []

    def visit(position: int, current: list[str]) -> None:
        if len(results) >= limit:
            return
        if position == covered:
            results.append(current.copy())
            return
        upper = min(position + _MAX_SYLLABLE_LENGTH, covered)
        for end in range(upper, position, -1):
            syllable = cleaned[position:end]
            if _valid_syllable(syllable) and reachable[end]:
                current.append(syllable)
                visit(end, current)
                current.pop()

    visit(0, [])
    return results, cleaned[covered:]


def segment_keys(keys: str) -> tuple[list[str] | None, str]:
    segmentations, fragment = all_segmentations(keys, limit=1)
    return (segmentations[0] if segmentations else None), fragment
