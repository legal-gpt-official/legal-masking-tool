from __future__ import annotations
import re
from typing import List, Optional

ADDRESS_SPLIT_RE = re.compile(r"(?P<pref>..??[都道府県])(?P<rest>.*)")


def load_list(path: str) -> List[str]:
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                t = line.strip()
                if t and not t.startswith("#"):
                    out.append(t)
    except FileNotFoundError:
        return []
    return out


def _longest_prefix_match(
    s: str, candidates: List[str]
) -> Optional[str]:
    for c in candidates:
        if s.startswith(c):
            return c
    return None


def mask_address_granular(
    original: str,
    granularity: str,
    prefectures: List[str],
    municipalities: List[str],
) -> str:
    s = original.strip()
    if not s:
        return s

    if granularity == "FULL_MASK":
        return "[ADDRESS]"

    pref = (
        _longest_prefix_match(s, prefectures) if prefectures else None
    )
    if pref:
        rest = s[len(pref):]
    else:
        m = ADDRESS_SPLIT_RE.match(s)
        if m:
            pref = m.group("pref")
            rest = m.group("rest")
        else:
            return "[ADDRESS]"

    if granularity == "UNTIL_PREF":
        return pref

    muni = None
    if municipalities:
        muni = _longest_prefix_match(pref + rest, municipalities)
        if muni and muni.startswith(pref):
            return muni

    m2 = re.match(r"^(.{1,10}?[市区町村])", rest)
    if m2:
        return pref + m2.group(1)

    return pref
