"""PDF pipeline with coordinate-based (Quad) redaction.

Previous approach:
    1. Extract full text with get_text()
    2. Run masking engine to get hits (start/end offsets)
    3. Re-search the PDF with page.search_for(term)  ← UNRELIABLE
       - Same term elsewhere gets wrongly redacted
       - Fragmented text blocks cause search misses

New approach:
    1. Extract text + per-character coordinates using get_text("rawdict")
    2. Build a global offset→(page, quad) map
    3. Run masking engine on the full text
    4. For each hit, look up the EXACT coordinates from the map
    5. Apply redactions at those precise positions → zero false positives

This eliminates both "search misses" and "wrong location redaction".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import fitz


# ---------------------------------------------------------------------------
# Character-to-coordinate mapping
# ---------------------------------------------------------------------------


@dataclass
class CharInfo:
    """A single character's position in the PDF."""
    page_idx: int
    x0: float
    y0: float
    x1: float
    y1: float
    char: str


@dataclass
class PageTextResult:
    """Text extraction result with character positions."""
    text: str
    chars: List[CharInfo] = field(default_factory=list)


def _extract_text_with_positions(doc: fitz.Document) -> PageTextResult:
    """Extract all text from a PDF with per-character coordinates.

    Returns a PageTextResult where:
      - text: the full document text (with \\n between pages/blocks/lines)
      - chars: list of CharInfo, one per character in `text`
              (newlines get dummy coordinates from the last real char)
    """
    all_chars: List[CharInfo] = []
    text_parts: List[str] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]

        # rawdict gives us blocks → lines → spans → chars with bbox
        try:
            page_dict = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        except Exception:
            # Fallback: use dict mode (slightly less granular)
            page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        blocks = page_dict.get("blocks", [])

        for block in blocks:
            if block.get("type") != 0:  # skip image blocks
                continue

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = span.get("text", "")
                    span_bbox = span.get("bbox", (0, 0, 0, 0))
                    span_chars = span.get("chars")

                    if span_chars:
                        # rawdict mode: per-character bbox available
                        for ch_info in span_chars:
                            c = ch_info.get("c", "")
                            bbox = ch_info.get("bbox", span_bbox)
                            if not c:
                                continue
                            ci = CharInfo(
                                page_idx=page_idx,
                                x0=bbox[0], y0=bbox[1],
                                x1=bbox[2], y1=bbox[3],
                                char=c,
                            )
                            all_chars.append(ci)
                            text_parts.append(c)
                    elif span_text:
                        # dict mode: distribute bbox evenly across characters
                        sx0, sy0, sx1, sy1 = span_bbox
                        n = max(len(span_text), 1)
                        char_w = (sx1 - sx0) / n
                        for i, c in enumerate(span_text):
                            ci = CharInfo(
                                page_idx=page_idx,
                                x0=sx0 + i * char_w, y0=sy0,
                                x1=sx0 + (i + 1) * char_w, y1=sy1,
                                char=c,
                            )
                            all_chars.append(ci)
                            text_parts.append(c)

                # End of line: add newline
                dummy = CharInfo(
                    page_idx=page_idx,
                    x0=0, y0=0, x1=0, y1=0,
                    char="\n",
                )
                all_chars.append(dummy)
                text_parts.append("\n")

        # End of page: add page break newline
        dummy = CharInfo(
            page_idx=page_idx,
            x0=0, y0=0, x1=0, y1=0,
            char="\n",
        )
        all_chars.append(dummy)
        text_parts.append("\n")

    return PageTextResult(
        text="".join(text_parts),
        chars=all_chars,
    )


def _get_quads_for_span(
    chars: List[CharInfo],
    start: int,
    end: int,
) -> Dict[int, List[fitz.Rect]]:
    """Get redaction rectangles for a character span.

    Returns {page_idx: [Rect, ...]} grouped by page.
    Merges adjacent characters on the same line into single rectangles.
    """
    if start < 0 or end > len(chars) or start >= end:
        return {}

    # Collect real chars (skip newlines)
    page_rects: Dict[int, List[fitz.Rect]] = {}

    current_page: Optional[int] = None
    current_y0: Optional[float] = None
    current_rect: Optional[List[float]] = None  # [x0, y0, x1, y1]

    SAME_LINE_TOLERANCE = 2.0  # pixels

    for i in range(start, end):
        ci = chars[i]
        if ci.char == "\n" or (ci.x0 == 0 and ci.y0 == 0 and ci.x1 == 0 and ci.y1 == 0):
            continue  # skip newline dummies

        if (
            current_rect is not None
            and ci.page_idx == current_page
            and current_y0 is not None
            and abs(ci.y0 - current_y0) < SAME_LINE_TOLERANCE
        ):
            # Same line: extend rectangle
            current_rect[2] = max(current_rect[2], ci.x1)
            current_rect[3] = max(current_rect[3], ci.y1)
            current_rect[0] = min(current_rect[0], ci.x0)
            current_rect[1] = min(current_rect[1], ci.y0)
        else:
            # Flush previous rect
            if current_rect is not None and current_page is not None:
                page_rects.setdefault(current_page, []).append(
                    fitz.Rect(current_rect)
                )
            # Start new rect
            current_page = ci.page_idx
            current_y0 = ci.y0
            current_rect = [ci.x0, ci.y0, ci.x1, ci.y1]

    # Flush last
    if current_rect is not None and current_page is not None:
        page_rects.setdefault(current_page, []).append(
            fitz.Rect(current_rect)
        )

    return page_rects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _japanese_ratio(s: str) -> float:
    if not s:
        return 0.0
    jp = 0
    for ch in s:
        o = ord(ch)
        if (0x3040 <= o <= 0x30FF) or (0x4E00 <= o <= 0x9FFF):
            jp += 1
    return jp / max(1, len(s))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def process_pdf_file(
    src_path: str, dst_path: str, engine
) -> Tuple[str, str, Dict[str, Any], str]:
    doc = fitz.open(src_path)

    # --- Step 1: Extract text with coordinate mapping ---
    extraction = _extract_text_with_positions(doc)
    full_text = extraction.text
    chars = extraction.chars

    report_warnings: List[str] = []

    # Japanese ratio check
    ratio = _japanese_ratio(full_text)
    policy = engine.policy
    jp_th = float(
        policy.get("pdf", {}).get("japanese_ratio_threshold", 0.2)
    )
    if ratio < jp_th:
        report_warnings.append("warning:pdf_low_japanese_ratio")

    # Character map availability check
    has_char_map = len(chars) > 0 and len(full_text) > 0
    if not has_char_map:
        report_warnings.append("warning:pdf_no_char_map")

    # --- Step 2: Run masking engine ---
    masked_text, report = engine.mask_text_with_report(
        full_text, doc_id=os.path.basename(src_path)
    )
    report["original_text_used"] = full_text
    report["masked_text_generated"] = masked_text
    report.setdefault("pdf_warnings", []).extend(report_warnings)

    # --- Step 3: Apply redactions using coordinate mapping ---
    pdf_conf = policy.get("pdf", {}) or {}
    max_rects = int(pdf_conf.get("max_rects_per_term", 50))

    stats = {
        "applied_rects": 0,
        "coord_mapped": 0,
        "search_fallback": 0,
        "search_misses": 0,
        "skipped_too_many": 0,
    }

    for h in report.get("hits", []):
        if str(h.get("reason", "")).startswith("keep"):
            continue

        start = int(h.get("start", 0))
        end = int(h.get("end", 0))
        term = h.get("original", "")

        if not term or start >= end:
            continue

        # Try coordinate-based mapping first
        if has_char_map and start < len(chars) and end <= len(chars):
            page_rects = _get_quads_for_span(chars, start, end)

            if page_rects:
                total_rects = sum(len(rs) for rs in page_rects.values())

                if total_rects > max_rects:
                    stats["skipped_too_many"] += 1
                    h["review_flag"] = True
                    h["reason"] = "warning:pdf_too_many_hits"
                    continue

                for pg_idx, rects in page_rects.items():
                    page = doc[pg_idx]
                    for r in rects:
                        # Add small padding for visual coverage
                        padded = fitz.Rect(
                            r.x0 - 0.5, r.y0 - 0.5,
                            r.x1 + 0.5, r.y1 + 0.5,
                        )
                        page.add_redact_annot(padded, fill=(0, 0, 0))
                    stats["applied_rects"] += len(rects)

                stats["coord_mapped"] += 1
                continue

        # Fallback: search_for (legacy method, for edge cases)
        min_len = int(pdf_conf.get("min_term_length", 2))
        if len(term.strip()) < min_len:
            continue

        found_any = False
        total_rects = 0
        rects_by_page: List[Tuple[int, list]] = []

        for i, page in enumerate(doc):
            rects = page.search_for(term)
            if rects:
                found_any = True
                total_rects += len(rects)
                rects_by_page.append((i, rects))

        if not found_any:
            stats["search_misses"] += 1
            h["review_flag"] = True
            h["reason"] = "warning:pdf_search_failed"
            continue

        if total_rects > max_rects:
            stats["skipped_too_many"] += 1
            h["review_flag"] = True
            h["reason"] = "warning:pdf_too_many_hits"
            continue

        for i, rects in rects_by_page:
            page = doc[i]
            for r in rects:
                page.add_redact_annot(r, fill=(0, 0, 0))
            stats["applied_rects"] += len(rects)

        stats["search_fallback"] += 1

    # --- Step 4: Apply all redactions (physical deletion) ---
    if stats["applied_rects"] > 0:
        for page in doc:
            page.apply_redactions()

    os.makedirs(
        os.path.dirname(os.path.abspath(dst_path)), exist_ok=True
    )
    doc.save(dst_path, deflate=True, garbage=4)
    doc.close()

    report["pdf_stats"] = stats
    return full_text, masked_text, report, dst_path
