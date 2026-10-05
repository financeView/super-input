"""Parse Rime ``speller/algebra`` derive rules into non-transitive groups.

The schema is the single source of truth. Each derive rule forms its own
relation group: pairs from different rules are deliberately not transitively
closed, matching one-step Rime fuzzy expansion semantics.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .syllables import SYLLABLES, norm


class FuzzyClasses:
    """Independent union-find groups for each supported derive rule."""

    def __init__(self, rule_groups: list[list[tuple[str, str]]]):
        self._groups: list[dict[str, str]] = []
        self._pairs: set[tuple[int, str, str]] = set()
        for group_index, pairs in enumerate(rule_groups):
            parent: dict[str, str] = {}
            for left, right in pairs:
                left, right = norm(left), norm(right)
                if left == right:
                    continue
                parent.setdefault(left, left)
                parent.setdefault(right, right)
                self._union(parent, left, right)
                self._pairs.add((group_index, *sorted((left, right))))
            self._groups.append(parent)
        self.pair_count = len(self._pairs)

    @staticmethod
    def _find(parent: dict[str, str], item: str) -> str:
        root = item
        while parent[root] != root:
            root = parent[root]
        while parent[item] != root:
            parent[item], item = root, parent[item]
        return root

    @classmethod
    def _union(cls, parent: dict[str, str], left: str, right: str) -> None:
        a, b = cls._find(parent, left), cls._find(parent, right)
        if a != b:
            parent[a] = b

    def _roots(self, item: str) -> list[tuple[int, str]]:
        roots = []
        for index, parent in enumerate(self._groups):
            if item in parent:
                roots.append((index, self._find(parent, item)))
        return roots or [(-1, item)]

    def match(self, a: str, b: str) -> bool:
        left, right = norm(a), norm(b)
        if left == right:
            return True
        return any(x == y for x in self._roots(left) for y in self._roots(right))


def load_fuzzy_classes(schema_path: str | Path) -> FuzzyClasses:
    """Load fuzzy relations from a Rime YAML schema.

    Supported rule grammar is ``derive/<regex>/<replacement>/`` with Rime's
    ``$1``-style capture references. Malformed derive rules fail loudly rather
    than silently disabling fuzzy matching.
    """
    path = Path(schema_path)
    with path.open(encoding="utf-8") as file:
        doc = yaml.safe_load(file)
    try:
        rules = doc["speller"]["algebra"]
    except (TypeError, KeyError) as exc:
        raise ValueError(f"schema has no speller/algebra: {path}") from exc
    if not isinstance(rules, list):
        raise ValueError("speller/algebra must be a list")

    groups: list[list[tuple[str, str]]] = []
    for rule in rules:
        if not isinstance(rule, str) or not rule.strip().startswith("derive/"):
            continue
        match = re.fullmatch(r"derive/(.*?)/(.*?)/", rule.strip())
        if not match:
            raise ValueError(f"unsupported derive rule syntax: {rule!r}")
        pattern, replacement = match.groups()
        try:
            regex = re.compile(pattern)
            replacement = re.sub(r"\$(\d)", r"\\\1", replacement)
        except re.error as exc:
            raise ValueError(f"invalid derive rule: {rule!r}") from exc
        pairs: set[tuple[str, str]] = set()
        for syllable in SYLLABLES:
            derived = norm(regex.sub(replacement, syllable))
            if derived != syllable and derived in SYLLABLES:
                pairs.add((syllable, derived))
        if pairs:
            groups.append(sorted(pairs))
    return FuzzyClasses(groups)
