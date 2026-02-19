from __future__ import annotations
import os
from typing import Tuple, Dict, Any, List

from .docx_segments import extract_docx_segments, Segment
from .docx_rewrite import rewrite_docx_with_maps

BLACK_CHAR = "\u25A0"  # ■


def _is_black_replacement(repl: str) -> bool:
    """Return True if replacement consists only of BLACK_CHAR (i.e., black-out mode)."""
    if not repl:
        return False
    return set(repl) == {BLACK_CHAR}


def map_hit_to_segments(
    hit: Dict[str, Any], segments: List[Segment]
) -> List[Dict[str, Any]]:
    """Map a global [start,end) hit to one or more DOCX segments.

    Previous implementation skipped hits crossing paragraph/run/cell boundaries.
    That caused UI-forced (manual) masks to be dropped at export time.
    This function returns *all* overlapping segments and provides local offsets.
    """
    s, e = int(hit["start"]), int(hit["end"])
    mapped: List[Dict[str, Any]] = []
    for seg in segments:
        # intersection with this segment
        os_ = max(s, seg.global_start)
        oe_ = min(e, seg.global_end)
        if os_ < oe_:
            mapped.append(
                {
                    "seg_id": seg.seg_id,
                    "local_start": os_ - seg.global_start,
                    "local_end": oe_ - seg.global_start,
                    "overlap": not (s >= seg.global_start and e <= seg.global_end),
                }
            )
    return mapped


def _piece_replacement(full_repl: str, piece_len: int) -> str:
    """Create replacement text for a split piece.

    - For black-out mode: keep length = piece_len.
    - For label mode: apply the same label to each piece (length may change).
    """
    if _is_black_replacement(full_repl):
        return BLACK_CHAR * max(0, int(piece_len))
    return full_repl


def process_docx_file(
    src_path: str, dst_path: str, engine
) -> Tuple[str, str, Dict[str, Any], str]:
    original_text, segments, docx_warnings = extract_docx_segments(src_path)

    masked_text, report = engine.mask_text_with_report(
        original_text, doc_id=os.path.basename(src_path)
    )

    report.setdefault("docx_warnings", []).extend(docx_warnings)
    report["original_text_used"] = original_text
    report["masked_text_generated"] = masked_text

    docx_maps: List[Dict[str, Any]] = []
    for h in report.get("hits", []):
        if str(h.get("reason", "")).startswith("keep"):
            continue

        maps = map_hit_to_segments(h, segments)
        if not maps:
            # Should not happen, but keep traceability
            h["review_flag"] = True
            h["reason"] = "warning:segment_not_found"
            continue

        # If a hit spans multiple segments, we still apply it by splitting into pieces.
        if len(maps) > 1 or any(m.get("overlap") for m in maps):
            h["review_flag"] = True
            # preserve original reason if exists, but note overlap for diagnostics
            h["reason"] = "warning:segment_overlap_applied"

        repl = h.get("replacement", "")
        for m in maps:
            piece_len = int(m["local_end"]) - int(m["local_start"])
            m2 = {
                "seg_id": m["seg_id"],
                "local_start": int(m["local_start"]),
                "local_end": int(m["local_end"]),
                "replacement": _piece_replacement(repl, piece_len),
            }
            docx_maps.append(m2)

    os.makedirs(os.path.dirname(os.path.abspath(dst_path)), exist_ok=True)
    rewrite_docx_with_maps(src_path, dst_path, docx_maps)
    return original_text, masked_text, report, dst_path
