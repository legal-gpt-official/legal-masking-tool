from __future__ import annotations
from typing import List, Optional
import re

from presidio_analyzer import PatternRecognizer, Pattern


def _load_terms(path: str, limit: int = 50000) -> List[str]:
    terms: List[str] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                t = line.strip()
                if not t or t.startswith("#"):
                    continue
                terms.append(t)
                if len(terms) >= limit:
                    break
    except FileNotFoundError:
        return []
    return terms


def _escape_regex(s: str) -> str:
    return re.escape(s)


def make_dict_recognizer(
    entity_type: str,
    dict_path: str,
    score: float = 0.99,
    name: Optional[str] = None,
    use_boundaries: bool = True,
) -> Optional[PatternRecognizer]:
    terms = _load_terms(dict_path)
    if not terms:
        return None

    terms.sort(key=len, reverse=True)
    alts = "|".join(_escape_regex(t) for t in terms)

    if use_boundaries:
        regex = rf"(?<!\w)({alts})(?!\w)"
    else:
        regex = rf"({alts})"

    rec = PatternRecognizer(
        supported_entity=entity_type,
        supported_language="ja",
        name=name or f"DICT_{entity_type}",
        patterns=[
            Pattern(
                name=f"dict_{entity_type}", regex=regex, score=score
            )
        ],
    )
    return rec


def build_custom_dict_recognizers(
    dict_dir: str,
) -> List[PatternRecognizer]:
    recs: List[PatternRecognizer] = []

    r1 = make_dict_recognizer(
        entity_type="COMPANY",
        dict_path=f"{dict_dir}/custom_companies.txt",
        score=0.995,
        name="CUSTOM_COMPANY_DICT",
        use_boundaries=True,
    )
    if r1:
        recs.append(r1)

    r2 = make_dict_recognizer(
        entity_type="KEYWORD",
        dict_path=f"{dict_dir}/custom_keywords.txt",
        score=0.99,
        name="CUSTOM_KEYWORD_DICT",
        use_boundaries=False,
    )
    if r2:
        recs.append(r2)

    return recs
