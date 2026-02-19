from __future__ import annotations
from typing import List, Dict, Any
import os

from .policy_loader import load_policy, dump_policy
from .atomic_io import atomic_write_text
from .audit_log import append_audit_log


def _append_line(path: str, term: str) -> None:
    os.makedirs(
        os.path.dirname(os.path.abspath(path)), exist_ok=True
    )
    term = (term or "").strip()
    if not term:
        return
    existing = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            existing = set(x.strip() for x in f if x.strip())
    if term in existing:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(term + "\n")


def apply_user_actions(
    policy_yaml_path: str,
    spans: List[Dict[str, Any]],
    user_actions: Dict[str, Any],
    custom_companies_path: str,
    audit_log_path: str,
) -> Dict[str, Any]:
    policy = load_policy(policy_yaml_path)
    allow_terms = (
        policy.setdefault("global", {})
        .setdefault("allowlist", {})
        .setdefault("terms", [])
    )

    spans_by_id = {s["span_id"]: s for s in spans}
    applied = []

    for act in user_actions.get("actions", []):
        sid = act.get("span_id")
        op = act.get("op")
        span = spans_by_id.get(sid)
        if not span:
            continue

        original = span.get("original", "")
        if op == "ALWAYS_KEEP":
            if original and original not in allow_terms:
                allow_terms.append(original)
                applied.append({"op": op, "term": original})
        elif op == "ALWAYS_MASK_AS_COMPANY":
            _append_line(custom_companies_path, original)
            applied.append({"op": op, "term": original})
        else:
            applied.append(
                {"op": op, "term": original, "skipped": True}
            )

    atomic_write_text(policy_yaml_path, dump_policy(policy))

    append_audit_log(
        audit_log_path,
        {
            "doc_id": user_actions.get("doc_id"),
            "actions": applied,
        },
    )

    return {"applied": applied, "policy_path": policy_yaml_path}
