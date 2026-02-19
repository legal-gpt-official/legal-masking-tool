from __future__ import annotations
from typing import List
from .normalize import normalize_term

MONEY_CTX_WORDS = [
    "円", "¥", "￥",
    "税込", "税抜", "合計", "総額",
    "対価", "報酬", "単価", "金額",
    "支払", "請求", "入金", "振込",
    "売買代金", "委託料", "利用料", "料金",
]


def has_money_context(
    text: str, start: int, end: int, window: int = 12
) -> bool:
    s = max(0, start - window)
    e = min(len(text), end + window)
    ctx = text[s:e]
    return any(w in ctx for w in MONEY_CTX_WORDS)


def in_list(term: str, allowlist: List[str]) -> bool:
    t = normalize_term(term)
    if not t:
        return False
    for a in allowlist:
        if t == normalize_term(a):
            return True
    return False
