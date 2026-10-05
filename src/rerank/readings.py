"""Han-character readings and fuzzy syllable comparison."""

from functools import lru_cache

from pypinyin import Style, pinyin

from .fuzzy import FuzzyClasses
from .syllables import norm


def _is_han(char: str) -> bool:
    cp = ord(char)
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x20000 <= cp <= 0x2FA1F
        or 0x30000 <= cp <= 0x323AF
    )


@lru_cache(maxsize=65536)
def _cached_readings(char: str) -> tuple[str, ...]:
    if len(char) != 1 or not _is_han(char):
        return ()
    result = pinyin(char, style=Style.NORMAL, heteronym=True, errors=lambda _: [])
    values = result[0] if result else []
    return tuple(dict.fromkeys(norm(value) for value in values if value))


def char_readings(ch: str) -> list[str]:
    """Return all known toneless readings for a single Han character."""
    return list(_cached_readings(ch))


def syllable_match(reading: str, typed: str, fuzzy: FuzzyClasses) -> bool:
    return fuzzy.match(reading, typed)
