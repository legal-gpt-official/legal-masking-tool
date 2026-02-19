from __future__ import annotations
import json
import os
from datetime import datetime, timezone


def append_audit_log(path: str, payload: dict) -> None:
    os.makedirs(
        os.path.dirname(os.path.abspath(path)), exist_ok=True
    )
    rec = dict(payload)
    rec["ts"] = datetime.now(timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
