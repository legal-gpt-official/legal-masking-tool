from __future__ import annotations
from typing import Any, Dict
from policy.policy_loader import load_policy as _load


def load_policy(path: str) -> Dict[str, Any]:
    return _load(path)
