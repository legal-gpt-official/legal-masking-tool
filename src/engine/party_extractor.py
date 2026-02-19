"""Party & role extractor for Japanese legal documents.

Extracts:
  1. Traditional party labels: 甲/乙/丙/丁
  2. Dynamic role definitions: 「以下『委託者』という」等
  3. Contract-defined aliases: 「以下『本契約』という」等

All extracted labels are returned as allowlist terms (these labels
should NOT be masked — they are structural elements of the contract).
The actual entity names (the company/person before the definition)
are returned separately for potential masking.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PartyDefinition:
    """A party or role definition found in the contract header."""
    label: str          # e.g. "甲", "委託者", "本契約"
    entity_name: str    # e.g. "株式会社ABC", "" (if no entity before)
    position: str       # e.g. "甲" → party position, "role" → dynamic role
    start: int = 0
    end: int = 0


@dataclass
class PartyExtractionResult:
    """Result of party/role extraction."""
    definitions: List[PartyDefinition] = field(default_factory=list)
    # Labels to add to allowlist (these should NOT be masked)
    allowlist_labels: List[str] = field(default_factory=list)
    # Entity names extracted from definitions (candidates for masking)
    self_names: List[str] = field(default_factory=list)
    counter_names: List[str] = field(default_factory=list)
    all_entity_names: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Traditional party labels
TRADITIONAL_LABELS = {"甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"}

# Pattern 1: XX株式会社（以下「甲」という）
#   The entity name typically starts after a separator (「と」「・」start of line, etc.)
#   and ends just before the parenthetical definition.
PARTY_DEF_PAT = re.compile(
    r"(?:^|[。、，,\n・と])\s*"    # entity start boundary
    r"(?P<entity>"
    r"(?:[^\s（(「『。、，,]{2,60}?)"  # entity name (avoid consuming parens/quotes)
    r")"
    r"\s*"
    r"(?:（|\()\s*"               # opening paren
    r"以下\s*"
    r"[「『｢\"]"                  # opening quote
    r"(?P<label>[^」』｣\"]{1,20})"  # label (1-20 chars)
    r"[」』｣\"]"                  # closing quote
    r"\s*という"
    r"\s*(?:。|）|\))",            # closing paren or period
    re.MULTILINE,
)

# Pattern 2: 以下「XX」という (without preceding entity, e.g. at start of clause)
ROLE_DEF_PAT = re.compile(
    r"以下\s*"
    r"[「『｢\"]"
    r"(?P<label>[^」』｣\"]{1,20})"
    r"[」』｣\"]"
    r"\s*という",
    re.MULTILINE,
)

# Pattern 3: 「甲」（XX株式会社）  — reverse order
REVERSE_PARTY_PAT = re.compile(
    r"[「『｢\"]"
    r"(?P<label>[^」』｣\"]{1,10})"
    r"[」』｣\"]\s*"
    r"(?:（|\()\s*"
    r"(?P<entity>.{2,60}?)"
    r"\s*(?:）|\))",
    re.MULTILINE,
)

# Common role names used in Japanese contracts
KNOWN_ROLE_NAMES = {
    "委託者", "受託者",
    "甲", "乙", "丙", "丁",
    "売主", "買主",
    "貸主", "借主",
    "賃貸人", "賃借人",
    "注文者", "請負人",
    "委任者", "受任者",
    "ライセンサー", "ライセンシー",
    "開示者", "受領者",
    "雇用者", "被雇用者",
    "出資者", "運営者",
    "本ベンダー", "本クライアント",
    "サービス提供者", "利用者",
}

# Contract structural terms (always allowlisted, never masked)
STRUCTURAL_TERMS = {
    "本契約", "本覚書", "本合意書", "本協定",
    "本規約", "本約款", "本誓約書",
    "本件", "本取引", "本業務", "本サービス",
    "本製品", "本ソフトウェア", "本システム",
    "本書", "本条", "本項",
}


# ---------------------------------------------------------------------------
# Extraction logic
# ---------------------------------------------------------------------------


def _clean_entity_name(s: str) -> str:
    """Clean up an entity name extracted from a party definition."""
    s = s.strip()

    # Remove common role prefixes like "委託者・" "受託者・"
    role_prefix_pat = re.compile(r"^(?:委託者|受託者|売主|買主|貸主|借主|甲|乙)[・:：]?\s*")
    s = role_prefix_pat.sub("", s).strip()

    # Loop: strip leading/trailing junk until stable
    prev = None
    while prev != s:
        prev = s
        for prefix in [
            "と", "及び", "および", "・", "、", "，",
            "\n", "\r", "）", ")",
        ]:
            while s.startswith(prefix) and len(s) > len(prefix):
                s = s[len(prefix):].strip()
        for suffix in ["は", "が", "の", "を", "に", "と"]:
            if s.endswith(suffix) and len(s) > 2:
                s = s[:-len(suffix)].strip()
    return s


def extract_parties(
    text: str,
    max_scan_chars: int = 8000,
) -> Tuple[List[str], List[str]]:
    """Extract party names and role definitions.

    Returns (self_names, counter_names) for backward compatibility.
    self_names = names associated with "甲" or first party
    counter_names = names associated with "乙" or second party

    Also populates the global allowlist with all labels found.
    """
    result = extract_parties_full(text, max_scan_chars)
    return result.self_names, result.counter_names


def extract_parties_full(
    text: str,
    max_scan_chars: int = 8000,
) -> PartyExtractionResult:
    """Full extraction with all metadata."""
    head = text[:max_scan_chars]
    result = PartyExtractionResult()
    seen_labels: set = set()

    # --- Pattern 1: Entity（以下「Label」という）---
    for m in PARTY_DEF_PAT.finditer(head):
        entity = _clean_entity_name(m.group("entity"))
        label = (m.group("label") or "").strip()

        if not label or len(label) > 20:
            continue
        if label in seen_labels:
            continue
        seen_labels.add(label)

        if label in TRADITIONAL_LABELS:
            position = label
        elif label in KNOWN_ROLE_NAMES:
            position = "role"
        elif label in STRUCTURAL_TERMS:
            position = "structural"
        else:
            position = "custom"

        defn = PartyDefinition(
            label=label,
            entity_name=entity if len(entity) >= 2 else "",
            position=position,
            start=m.start(),
            end=m.end(),
        )
        result.definitions.append(defn)
        result.allowlist_labels.append(label)

        if entity and len(entity) >= 2:
            result.all_entity_names.append(entity)
            if label == "甲" or position == "role" and len(result.self_names) == 0:
                result.self_names.append(entity)
            elif label == "乙":
                result.counter_names.append(entity)

    # --- Pattern 3: Reverse order 「Label」（Entity） ---
    for m in REVERSE_PARTY_PAT.finditer(head):
        label = (m.group("label") or "").strip()
        entity = _clean_entity_name(m.group("entity"))

        if not label or label in seen_labels:
            continue
        seen_labels.add(label)

        defn = PartyDefinition(
            label=label,
            entity_name=entity if len(entity) >= 2 else "",
            position=label if label in TRADITIONAL_LABELS else "custom",
            start=m.start(),
            end=m.end(),
        )
        result.definitions.append(defn)
        result.allowlist_labels.append(label)

        if entity and len(entity) >= 2:
            result.all_entity_names.append(entity)

    # --- Pattern 2: Standalone 以下「Label」という (no entity) ---
    for m in ROLE_DEF_PAT.finditer(head):
        label = (m.group("label") or "").strip()
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)

        defn = PartyDefinition(
            label=label,
            entity_name="",
            position="role" if label in KNOWN_ROLE_NAMES else "structural" if label in STRUCTURAL_TERMS else "custom",
            start=m.start(),
            end=m.end(),
        )
        result.definitions.append(defn)
        result.allowlist_labels.append(label)

    # --- Always add traditional labels + structural terms to allowlist ---
    for t in TRADITIONAL_LABELS:
        if t not in result.allowlist_labels:
            result.allowlist_labels.append(t)

    for t in STRUCTURAL_TERMS:
        if t not in result.allowlist_labels:
            result.allowlist_labels.append(t)

    # --- Deduplicate ---
    result.allowlist_labels = list(dict.fromkeys(result.allowlist_labels))
    result.self_names = list(dict.fromkeys(result.self_names))
    result.counter_names = list(dict.fromkeys(result.counter_names))
    result.all_entity_names = list(dict.fromkeys(result.all_entity_names))

    return result
