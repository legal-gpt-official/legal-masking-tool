from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import re


@dataclass(frozen=True)
class FastPattern:
    entity_type: str
    name: str
    regex: str
    score: float


def default_patterns() -> List[FastPattern]:
    # Keep in sync with engine/recognizers.py (but independent from Presidio)
    return [
        FastPattern("EMAIL", "email_regex",
            r"(?<![\w\-\.])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![\w\-\.])", 0.99),
        FastPattern("PHONE", "phone_regex",
            r"(?<!\d)(0\d{1,4}[-\u30FC]?\d{1,4}[-\u30FC]?\d{3,4})(?!\d)", 0.85),
        FastPattern("ID", "jp_postal",
            r"(?<!\d)(\d{3}[-\u30FC]?\d{4})(?!\d)", 0.95),
        FastPattern("ID", "compact_id",
            r"(?<![A-Za-z0-9])([A-Z]{1,3}\d{2,6})(?![A-Za-z0-9])", 0.80),
        FastPattern("ID", "hyphenated_id",
            r"(?<![A-Za-z0-9])([A-Z]{2,10}-\d{2,4}(?:-[A-Z0-9]{1,6}){1,6})(?![A-Za-z0-9])", 0.85),
        FastPattern("PERSON", "jp_name_line_with_space",
            r"(?m)^[\t \u3000]*[一-龥]{1,4}[\t \u0020\u3000]+[一-龥]{1,4}[\t \u3000]*$", 0.86),
        FastPattern("PERSON", "tanto_single_surname",
            r"(?<=担当[:：])[一-龥]{2,4}", 0.82),
        FastPattern("PERSON", "tanto_single_surname_paren",
            r"(?<=\(担当[:：])[一-龥]{2,4}(?=\))", 0.80),
        FastPattern("PERSON", "tanto_single_surname_fwparen",
            r"(?<=（担当[:：])[一-龥]{2,4}(?=）)", 0.80),
        FastPattern("ID", "age_after_colon",
            r"(?<=年齢[:：])\d{1,3}", 0.75),
        FastPattern("ID", "age_standalone_line_before_gender",
            r"(?m)(?<=\n)\d{1,3}(?=\n(?:男|女)\n)", 0.78),
        FastPattern("MONEY", "money_amount",
            r"(?:"
            r"(?:[¥￥]\s*(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
            r"|"
            r"(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\s*(?:円|万円|千円|百万円))"
            r")", 0.85),
        FastPattern("DATE", "ymd",
            r"\d{4}[\/\.\-\u5E74]\s*\d{1,2}[\/\.\-\u6708]\s*\d{1,2}\s*(\u65E5)?", 0.80),
        FastPattern("DATE", "wareki",
            r"(\u4EE4\u548C|\u5E73\u6210|\u662D\u548C|R|H|S)\s*(\d{1,2}|\u5143)\s*\u5E74", 0.75),
        FastPattern("ADDRESS", "addr_hint",
            r"(..??[\u90FD\u9053\u5E9C\u770C].{1,30}?[\u5E02\u533A\u753A\u6751].{0,40})", 0.55),
        FastPattern("COMPANY", "kabushiki_1",
            r"(\u682A\u5F0F\u4F1A\u793E|\u6709\u9650\u4F1A\u793E|\u5408\u540C\u4F1A\u793E)\s*\S{1,30}", 0.70),
        FastPattern("COMPANY", "kabushiki_2",
            r"\S{1,30}\s*(\u682A\u5F0F\u4F1A\u793E|\u6709\u9650\u4F1A\u793E|\u5408\u540C\u4F1A\u793E)", 0.70),
        FastPattern("COMPANY", "abbr",
            r"(\uFF08\u682A\uFF09|\(\u682A\))\s*\S{1,30}", 0.65),
        FastPattern("PARTIES", "parties",
            r"(?<!\w)(\u7532|\u4E59|\u4E19|\u4E01)(?!\w)", 0.99),
    ]


class FastRegexAnalyzer:
    """High-throughput regex analyzer (no Presidio / no spaCy).

    Intended for long documents where GUI responsiveness or throughput matters
    more than advanced NLP features.
    """

    def __init__(self, patterns: Optional[List[FastPattern]] = None):
        self._patterns = patterns or default_patterns()
        self._compiled: List[Tuple[FastPattern, re.Pattern]] = []
        for p in self._patterns:
            self._compiled.append((p, re.compile(p.regex)))

    def analyze(
        self,
        text: str,
        allow_list: Optional[List[str]] = None,
    ) -> List[Dict[str, object]]:
        allow = set(allow_list or [])
        out: List[Dict[str, object]] = []
        for p, cre in self._compiled:
            for m in cre.finditer(text):
                s, e = m.start(), m.end()
                if s < 0 or e <= s:
                    continue
                original = text[s:e]
                if original in allow:
                    continue
                out.append(
                    {
                        "start": s,
                        "end": e,
                        "entity_type": p.entity_type,
                        "score": float(p.score),
                        "pattern": p.name,
                        "source": "fast_regex",
                    }
                )
        # caller resolves overlaps
        out.sort(key=lambda x: (int(x["start"]), -(int(x["end"]) - int(x["start"]))))
        return out
