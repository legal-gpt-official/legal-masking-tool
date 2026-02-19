from __future__ import annotations
import json
import os
from typing import Dict, Any, List


def _context_preview(
    text: str, start: int, end: int, window: int = 24
) -> str:
    s = max(0, start - window)
    e = min(len(text), end + window)
    return text[s:e].replace("\n", " ")


def build_review_payload(
    doc_id: str,
    original_text: str,
    masked_text: str,
    report: Dict[str, Any],
) -> Dict[str, Any]:
    spans: List[Dict[str, Any]] = []
    review_items: List[Dict[str, Any]] = []

    for i, h in enumerate(report.get("hits", []), start=1):
        sid = f"span_{i:06d}"
        mark_id = f"m{i:06d}"
        span = {
            "span_id": sid,
            "mark_id": mark_id,
            "doc_id": doc_id,
            "entity_type": h.get("entity_type"),
            "start": int(h.get("start")),
            "end": int(h.get("end")),
            "original": h.get("original", ""),
            "replacement": h.get("replacement", ""),
            "score": float(h.get("score", 0.0) or 0.0),
            "reason": h.get("reason", ""),
            "source": h.get("source", "analyzer"),
        }
        spans.append(span)

    raw_review = report.get("review")
    if raw_review is None:
        raw_review = []
        for h in report.get("hits", []):
            sc = float(h.get("score", 0.0) or 0.0)
            if (
                sc
                and sc
                < float(report.get("review_threshold", 0.8))
            ) or h.get("review_flag"):
                raw_review.append(h)

    for j, h in enumerate(raw_review, start=1):
        match = next(
            (
                s
                for s in spans
                if s["start"] == h.get("start")
                and s["end"] == h.get("end")
                and s["entity_type"] == h.get("entity_type")
            ),
            None,
        )
        if not match:
            continue
        rid = f"rev_{j:06d}"
        review_items.append(
            {
                "id": rid,
                "span_id": match["span_id"],
                "mark_id": match["mark_id"],
                "entity_type": match["entity_type"],
                "original": match["original"],
                "replacement": match["replacement"],
                "score": match["score"],
                "reason": match["reason"],
                "context_preview": _context_preview(
                    original_text, match["start"], match["end"]
                ),
                "offset": [match["start"], match["end"]],
            }
        )

    payload = {
        "doc_id": doc_id,
        "party_auto": report.get("party_auto", {}),
        "summary": report.get("summary", {}),
        "spans": spans,
        "review_items": review_items,
        "warnings": {
            "docx": report.get("docx_warnings", []),
            "pdf": report.get("pdf_warnings", []),
        },
    }
    return payload


def save_json(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(
        os.path.dirname(os.path.abspath(path)), exist_ok=True
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
