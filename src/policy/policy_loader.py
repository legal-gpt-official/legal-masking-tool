from __future__ import annotations
import yaml
from typing import Any, Dict


def load_policy(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dump_policy(policy: Dict[str, Any]) -> str:
    return yaml.safe_dump(
        policy, allow_unicode=True, sort_keys=False
    )
