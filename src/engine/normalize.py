from __future__ import annotations
import re
import unicodedata

_WS_RE = re.compile(r"\s+")


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def normalize_term(s: str) -> str:
    """allowlist照合・stable id等で統一利用"""
    s = nfkc(s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def normalize_text_for_analysis(text: str) -> str:
    """解析前の正規化（オフセットを壊さないので加工しない）"""
    return text
