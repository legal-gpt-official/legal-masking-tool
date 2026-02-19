from __future__ import annotations
import re

WAREKI_RE = re.compile(
    r"(令和|平成|昭和|R|H|S)\s*(\d{1,2}|元)\s*年"
)
YMD_RE = re.compile(
    r"(\d{4})[\/\.\-年]\s*(\d{1,2})[\/\.\-月]\s*(\d{1,2})\s*(日)?"
)


def date_granular(original: str, mode: str = "YEAR") -> str:
    s = original.strip()
    if mode == "FULL_MASK":
        return "[DATE]"

    m = WAREKI_RE.search(s)
    if m:
        g, y = m.group(1), m.group(2)
        return f"{g}{y}年"

    m2 = YMD_RE.search(s)
    if m2:
        y, mo = m2.group(1), m2.group(2)
        if mode == "YEAR":
            return f"{y}年"
        if mode == "YM":
            return f"{y}年{int(mo)}月"

    return "[DATE]"
