from __future__ import annotations
import os
import chardet
from typing import Tuple, Dict, Any


def _read_text_auto(path: str) -> str:
    raw = open(path, "rb").read()
    det = chardet.detect(raw)
    enc = det.get("encoding") or "utf-8"
    try:
        return raw.decode(enc, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def process_text_file(
    src_path: str, dst_path: str, engine
) -> Tuple[str, str, Dict[str, Any], str]:
    original = _read_text_auto(src_path)
    masked, report = engine.mask_text_with_report(
        original, doc_id=os.path.basename(src_path)
    )
    os.makedirs(
        os.path.dirname(os.path.abspath(dst_path)), exist_ok=True
    )
    with open(dst_path, "w", encoding="utf-8") as f:
        f.write(masked)
    report["masked_text_generated"] = masked
    report["original_text_used"] = original
    return original, masked, report, dst_path
