from __future__ import annotations
import csv
import os
import shutil
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from pipelines.text_pipeline import process_text_file
from pipelines.docx_pipeline import process_docx_file
from pipelines.pdf_pipeline import process_pdf_file
from report.report_exporter import export_html_side_by_side
from report.ui_payload import build_review_payload, save_json
from policy.audit_log import append_audit_log


@dataclass
class ProcessResult:
    original_text: str
    masked_text: str
    report: Dict[str, Any]
    out_masked_path: str
    out_report_html: str
    out_payload_json: str
    out_csv_path: str


def _ensure_dirs(base_dir: str) -> Dict[str, str]:
    out_dir = os.path.join(base_dir, "output")
    backup_dir = os.path.join(out_dir, "backup")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)
    return {"out": out_dir, "backup": backup_dir}


def _safe_basename(path: str) -> str:
    r"""Return a filesystem-safe basename for outputs.

    Windows forbids: < > : " / \ | ? *
    Also strips control chars and collapses dangerous sequences.
    """
    b = os.path.basename(path)
    b = b.replace("..", "_").replace("/", "_").replace("\\", "_")
    b = re.sub(r'[<>:"/\\|?*]', "_", b)
    b = re.sub(r"[\x00-\x1f]", "_", b)
    b = b.rstrip(" .")
    if not b:
        b = "document"
    return b


def _export_hits_csv(hits: List[Dict[str, Any]], out_path: str) -> None:
    """Export detection hits to CSV for external audit/review."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fields = [
        "entity_type", "start", "end", "original",
        "replacement", "score", "reason", "source",
    ]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for h in hits:
            w.writerow(h)


class AppController:
    def __init__(self, base_dir: str, engine, log_fn: Optional[Callable[[str], None]] = None):
        self.base_dir = base_dir
        self.engine = engine
        self.log = log_fn or (lambda _: None)
        dirs = _ensure_dirs(base_dir)
        self.out_dir = dirs["out"]
        self.backup_dir = dirs["backup"]
        self.audit_log_path = os.path.join(base_dir, "audit_log.jsonl")

    def process_file(self, file_path: str) -> ProcessResult:
        ext = os.path.splitext(file_path)[1].lower()
        base = _safe_basename(file_path)

        self.log(f"backup: {base}")
        try:
            shutil.copy2(file_path, os.path.join(self.backup_dir, base))
        except Exception:
            pass

        masked_path = os.path.join(self.out_dir, f"masked_{base}")
        report_html = os.path.join(self.out_dir, f"report_{base}.html")
        payload_json = os.path.join(self.out_dir, f"review_payload_{base}.json")
        csv_path = os.path.join(self.out_dir, f"hits_{base}.csv")

        self.log(f"pipeline: {ext}")
        if ext == ".docx":
            original_text, masked_text, report, out_path = (
                process_docx_file(file_path, masked_path, self.engine)
            )
        elif ext == ".pdf":
            original_text, masked_text, report, out_path = (
                process_pdf_file(file_path, masked_path, self.engine)
            )
        else:
            original_text, masked_text, report, out_path = (
                process_text_file(file_path, masked_path, self.engine)
            )

        self.log("exporting HTML report")
        export_html_side_by_side(
            original_text=original_text,
            masked_text=masked_text,
            report=report,
            out_html_path=report_html,
        )

        self.log("exporting review payload")
        payload = build_review_payload(
            doc_id=base,
            original_text=original_text,
            masked_text=masked_text,
            report=report,
        )
        save_json(payload_json, payload)

        self.log("exporting CSV")
        _export_hits_csv(report.get("hits", []), csv_path)

        # audit log
        append_audit_log(
            self.audit_log_path,
            {
                "action": "process_file",
                "doc_id": base,
                "total_hits": len(report.get("hits", [])),
                "review_hits": len(report.get("review", [])),
            },
        )

        self.log("done")
        return ProcessResult(
            original_text=original_text,
            masked_text=masked_text,
            report=report,
            out_masked_path=out_path,
            out_report_html=report_html,
            out_payload_json=payload_json,
            out_csv_path=csv_path,
        )
