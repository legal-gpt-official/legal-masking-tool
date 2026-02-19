from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Tuple
from .normalize import normalize_term


@dataclass
class StableIdState:
    counters: Dict[str, int] = field(default_factory=dict)
    mapping: Dict[Tuple[str, str], str] = field(default_factory=dict)

    @classmethod
    def create(cls) -> "StableIdState":
        return cls()

    def get_label(
        self, entity: str, original: str, label_format: Dict[str, str]
    ) -> str:
        key = (entity, normalize_term(original))
        if key in self.mapping:
            return self.mapping[key]

        n = self.counters.get(entity, 0) + 1
        self.counters[entity] = n

        fmt = label_format.get(entity, f"[{entity}_{{n:02d}}]")
        label = fmt.format(n=n)
        self.mapping[key] = label
        return label
