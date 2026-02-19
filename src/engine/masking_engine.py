from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from presidio_analyzer import RecognizerResult

from .presidio_factory import build_analyzer
from .policy import load_policy
from .stable_id import StableIdState
from .text_rules import has_money_context, in_list
from .address_rules import load_list, mask_address_granular
from .date_rules import date_granular
from .fast_regex import FastRegexAnalyzer

BLACK_CHAR = "\u25A0"  # ■


@dataclass
class RuntimeOverrides:
    once_allowlist: List[str]
    forced_masks: List[Dict[str, Any]]
    # Span-level keep (masking off) overrides: list of {start:int, end:int}
    keep_spans: List[Dict[str, int]]


def _count_by_entity(hits: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for h in hits:
        e = h.get("entity_type") or "UNKNOWN"
        out[e] = out.get(e, 0) + 1
    return out


def _normalize_forced_masks(
    forced_masks: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    out = []
    for fm in forced_masks or []:
        try:
            s = int(fm["start"])
            e = int(fm["end"])
            if 0 <= s < e:
                out.append(
                    {
                        "start": s,
                        "end": e,
                        "entity_type": fm.get("entity_type", "CUSTOM"),
                        "label": fm.get("label", None),
                        "reason": fm.get("reason", "forced:mask_once"),
                    }
                )
        except Exception:
            continue
    return out


class MaskingEngine:
    def __init__(self, policy_path: str, base_dir: str, log_fn=None):
        self.policy_path = policy_path
        self.base_dir = base_dir
        self.policy = load_policy(policy_path)
        self._log = log_fn or (lambda _: None)

        # entity priority (overlap resolution)
        # policy.yaml の entities[].priority を参照。未定義は 0。
        self.entity_priority: Dict[str, int] = {
            (e.get("name") or ""): int(e.get("priority", 0) or 0)
            for e in (self.policy.get("entities") or [])
            if isinstance(e, dict)
        }

        # dict_dir は build_analyzer の前に定義する（前回バグの修正箇所）
        dict_dir = self.policy.get("dict_dir") or (
            base_dir + "/resources/dict"
        )
        self.dict_dir = dict_dir

        # Try full NLP engine; fall back to regex-only if it fails
        self.nlp_available = False
        try:
            self.analyzer = build_analyzer(dict_dir=dict_dir)
            self.nlp_available = True
            if log_fn:
                log_fn("NLP engine loaded (Presidio + GiNZA)")
        except Exception as nlp_err:
            self.analyzer = None
            if log_fn:
                log_fn(f"WARNING: NLP engine failed: {nlp_err}")
                log_fn("Falling back to regex-only mode (reduced accuracy)")

        # fast analyzer (regex only) for long documents or fallback
        self.fast_analyzer = FastRegexAnalyzer()
        perf = self.policy.get('performance', {}) or {}
        # NLP chunk size: each chunk processed with full Presidio+GiNZA
        # spaCy tokenizer limit: 49,149 bytes. Japanese ≈ 3 bytes/char → max ~16K chars.
        # Use 15,000 for safety margin.
        self.nlp_chunk_size = int(perf.get('nlp_chunk_size', 15000) or 15000)
        self.nlp_chunk_overlap = int(perf.get('nlp_chunk_overlap', 300) or 300)
        # Only fall back to regex-only for extremely large files (5x previous limit)
        self.fast_threshold_chars = int(perf.get('fast_threshold_chars', 400000) or 400000)
        self.force_fast = bool(perf.get('force_fast', False))

        self.runtime = RuntimeOverrides(
            once_allowlist=[], forced_masks=[], keep_spans=[]
        )

        # 住所辞書
        self.prefectures = load_list(f"{dict_dir}/prefectures.txt")
        self.municipalities = load_list(f"{dict_dir}/municipalities.txt")

    def set_runtime_overrides(
        self,
        once_allowlist: List[str],
        forced_masks: List[Dict[str, Any]],
        keep_spans: Optional[List[Dict[str, int]]] = None,
    ) -> None:
        self.runtime = RuntimeOverrides(
            once_allowlist=once_allowlist or [],
            forced_masks=forced_masks or [],
            keep_spans=[
                {
                    "start": int(x.get("start")),
                    "end": int(x.get("end")),
                }
                for x in (keep_spans or [])
                if x is not None
                and isinstance(x, dict)
                and 0 <= int(x.get("start", -1)) < int(x.get("end", -1))
            ],
        )

    @staticmethod
    def _overlaps_any_keep(start: int, end: int, keep_spans: List[Dict[str, int]]) -> bool:
        for ks in keep_spans or []:
            try:
                s = int(ks.get("start"))
                e = int(ks.get("end"))
                if start < e and end > s:
                    return True
            except Exception:
                continue
        return False

    def _merge_overlaps(
        self, results: List[RecognizerResult]
    ) -> List[RecognizerResult]:
        rs = sorted(
            results, key=lambda r: (r.start, -(r.end - r.start))
        )
        merged = []
        for r in rs:
            if not merged:
                merged.append(r)
                continue
            prev = merged[-1]
            if r.start < prev.end:
                # overlap: prefer higher priority, then longer span, then higher score
                p_new = int(self.entity_priority.get(getattr(r, "entity_type", "") or "", 0))
                p_prev = int(self.entity_priority.get(getattr(prev, "entity_type", "") or "", 0))
                len_new = (r.end - r.start)
                len_prev = (prev.end - prev.start)
                s_new = float(getattr(r, "score", 0.0) or 0.0)
                s_prev = float(getattr(prev, "score", 0.0) or 0.0)
                if (p_new, len_new, s_new) > (p_prev, len_prev, s_prev):
                    merged[-1] = r
            else:
                merged.append(r)
        return merged

    # ------------------------------------------------------------------
    # Chunked NLP analysis for large documents
    # ------------------------------------------------------------------

    @staticmethod
    def _split_into_chunks(
        text: str,
        chunk_size: int,
        overlap: int,
    ) -> List[Tuple[int, str]]:
        """Split text into overlapping chunks at paragraph boundaries.

        Returns list of (offset, chunk_text) tuples.
        Each chunk is at most chunk_size chars, split at the nearest
        paragraph break (\\n) to avoid cutting entities.
        """
        if len(text) <= chunk_size:
            return [(0, text)]

        chunks: List[Tuple[int, str]] = []
        pos = 0
        text_len = len(text)

        while pos < text_len:
            end = min(pos + chunk_size, text_len)

            # Try to break at a paragraph boundary
            if end < text_len:
                # Search backward from end for a newline
                break_at = text.rfind("\n", pos + chunk_size // 2, end)
                if break_at > pos:
                    end = break_at + 1  # include the newline

            chunks.append((pos, text[pos:end]))

            # Advance with overlap
            next_pos = end - overlap
            if next_pos <= pos:
                next_pos = end  # avoid infinite loop
            pos = next_pos

        return chunks

    def _analyze_chunked(
        self,
        text: str,
        allowlist: List[str],
    ) -> List[Dict[str, Any]]:
        """Analyze large text by splitting into chunks and processing
        each chunk with full Presidio+GiNZA NLP.

        Results from overlapping zones are deduplicated by preferring
        the version from the chunk where the entity is fully contained
        (not at the edge).
        """
        chunks = self._split_into_chunks(
            text, self.nlp_chunk_size, self.nlp_chunk_overlap,
        )

        all_results: List[Dict[str, Any]] = []
        total_chunks = len(chunks)
        self._log(f"chunked NLP: {total_chunks} chunks ({len(text):,} chars)")

        for ci, (chunk_offset, chunk_text) in enumerate(chunks, 1):
            self._log(f"  chunk {ci}/{total_chunks} (offset={chunk_offset:,}, len={len(chunk_text):,})")
            try:
                results = self.analyzer.analyze(
                    text=chunk_text, language="ja", allow_list=allowlist,
                )
                merged = self._merge_overlaps(results)
                for r in merged:
                    all_results.append({
                        "start": r.start + chunk_offset,
                        "end": r.end + chunk_offset,
                        "entity_type": r.entity_type,
                        "score": float(getattr(r, "score", 0.0) or 0.0),
                        "source": "analyzer",
                    })
            except Exception:
                # If a chunk fails (e.g., memory), fall back to regex for that chunk
                try:
                    fast_results = self.fast_analyzer.analyze(
                        text=chunk_text, allow_list=allowlist,
                    )
                    for r in (fast_results or []):
                        all_results.append({
                            "start": int(r["start"]) + chunk_offset,
                            "end": int(r["end"]) + chunk_offset,
                            "entity_type": str(r["entity_type"]),
                            "score": float(r.get("score", 0.0) or 0.0),
                            "source": "analyzer",
                            "pattern": r.get("pattern"),
                        })
                except Exception:
                    continue

        # Deduplicate: sort by start, then resolve overlaps
        all_results.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
        deduped: List[Dict[str, Any]] = []
        for r in all_results:
            if not deduped:
                deduped.append(r)
                continue
            prev = deduped[-1]
            if r["start"] < prev["end"]:
                # Overlap from chunk boundary: keep the one with higher score/priority
                p_new = int(self.entity_priority.get(r.get("entity_type", ""), 0))
                p_prev = int(self.entity_priority.get(prev.get("entity_type", ""), 0))
                len_new = r["end"] - r["start"]
                len_prev = prev["end"] - prev["start"]
                s_new = float(r.get("score", 0.0))
                s_prev = float(prev.get("score", 0.0))
                if (p_new, len_new, s_new) > (p_prev, len_prev, s_prev):
                    deduped[-1] = r
            else:
                deduped.append(r)

        return deduped

    def mask_text_with_report(
        self,
        text: str,
        doc_id: str = "doc",
    ) -> Tuple[str, Dict[str, Any]]:
        state = StableIdState.create()

        base_allowlist = list(
            self.policy.get("global", {})
            .get("allowlist", {})
            .get("terms", [])
            or []
        )

        # party auto-detection (expanded: roles + structural terms)
        from .party_extractor import extract_parties_full
        party_result = extract_parties_full(text)
        self_names = party_result.self_names
        party_labels = party_result.allowlist_labels  # 甲乙 + 委託者 + 本契約 etc.

        allowlist = list(
            dict.fromkeys(
                base_allowlist
                + self_names
                + party_labels
                + (self.runtime.once_allowlist or [])
            )
        )

        
        # analyzer: 3-tier strategy based on text length
        #   - small  (< nlp_chunk_size):     full NLP in one pass
        #   - medium (< fast_threshold):     chunked NLP (split + merge)
        #   - huge   (>= fast_threshold):    regex-only fallback
        use_fast = self.force_fast or (not self.nlp_available) or (len(text) >= self.fast_threshold_chars)
        use_chunked = (
            not use_fast
            and len(text) >= self.nlp_chunk_size
        )

        if use_fast:
            if not self.nlp_available:
                self._log("analysis: regex-only mode (NLP engine not available)")
            else:
                self._log(f"analysis: regex-only mode ({len(text):,} chars >= {self.fast_threshold_chars:,} threshold)")
        elif use_chunked:
            self._log(f"analysis: chunked NLP mode ({len(text):,} chars)")
        else:
            self._log(f"analysis: full NLP mode ({len(text):,} chars)")

        candidates: List[Dict[str, Any]] = []

        if use_fast:
            merged_fast = self.fast_analyzer.analyze(text=text, allow_list=allowlist)
            for r in (merged_fast or []):
                candidates.append(
                    {
                        "start": int(r["start"]),
                        "end": int(r["end"]),
                        "entity_type": str(r["entity_type"]),
                        "score": float(r.get("score", 0.0) or 0.0),
                        "source": "analyzer",
                        "pattern": r.get("pattern"),
                    }
                )
        elif use_chunked:
            # Chunked NLP: split into overlapping chunks, analyze each
            # with full Presidio+GiNZA, then merge with deduplication
            candidates = self._analyze_chunked(text, allowlist)
        else:
            results = self.analyzer.analyze(text=text, language="ja", allow_list=allowlist)
            merged = self._merge_overlaps(results)
            for r in merged:
                candidates.append(
                    {
                        "start": r.start,
                        "end": r.end,
                        "entity_type": r.entity_type,
                        "score": float(getattr(r, "score", 0.0) or 0.0),
                        "source": "analyzer",
                    }
                )

        forced = _normalize_forced_masks(self.runtime.forced_masks)
        for fm in forced:
            candidates.append(
                {
                    "start": fm["start"],
                    "end": fm["end"],
                    "entity_type": fm["entity_type"],
                    "score": 1.0,
                    "source": "forced",
                    "label": fm.get("label"),
                    "forced_reason": fm.get("reason"),
                }
            )

        # resolve overlaps:
        #   forced > (priority) > (span length) > (score)
        # NOTE:
        #   旧実装は「長いスパン優先」で先に確定してしまい、
        #   低精度の MONEY が他エンティティを潰すことがあった。
        def _cand_key(x: Dict[str, Any]) -> Tuple[int, int, int, float]:
            src_rank = 0 if x.get("source") == "forced" else 1
            pr = int(self.entity_priority.get(x.get("entity_type") or "", 0) or 0)
            ln = int((x.get("end") or 0) - (x.get("start") or 0))
            sc = float(x.get("score", 0.0) or 0.0)
            # sort asc by start separately
            return (src_rank, -pr, -ln, -sc)

        candidates = sorted(candidates, key=lambda x: (x["start"],) + _cand_key(x))
        resolved: List[Dict[str, Any]] = []
        for c in candidates:
            if not resolved:
                resolved.append(c)
                continue
            prev = resolved[-1]
            if c["start"] < prev["end"]:
                # overlap: keep the "better" one
                if _cand_key(c) < _cand_key(prev):
                    # _cand_key() is ordered so that "better" is smaller
                    resolved[-1] = c
            else:
                resolved.append(c)

        # span-level keep overrides: if a span overlaps a keep_span, do not mask it.
        # (Used by GUI toggles to disable masking for a specific detection.)
        keep_spans = self.runtime.keep_spans or []
        if keep_spans:
            def _overlaps(a_s: int, a_e: int, b_s: int, b_e: int) -> bool:
                return a_s < b_e and a_e > b_s

            resolved = [
                r
                for r in resolved
                if not any(_overlaps(r["start"], r["end"], ks["start"], ks["end"]) for ks in keep_spans)
            ]

        out = []
        hits = []
        review = []
        last = 0

        output_conf = self.policy.get("output", {}) or {}
        mode = output_conf.get("mode", "LABEL")
        black_min_len = int(output_conf.get("black_min_len", 3))
        label_format = output_conf.get("label_format", {}) or {}
        addr_conf = self.policy.get("address", {}) or {}
        addr_gran = addr_conf.get("granularity", "UNTIL_CITY")

        review_th = float(
            self.policy.get("review", {}).get("threshold", 0.8)
        )

        for r in resolved:
            start, end = r["start"], r["end"]
            entity = r["entity_type"]
            score = float(r.get("score", 0.0) or 0.0)

            # --- Heuristic span expansion (契約書の会社名でよくある崩れ対策) ---
            # Analyzer が「株式会社」などの法人格部分だけを COMPANY として
            # 抜いてしまう場合があり、そのままだと「[COMPANY]明和エンジニアリング」
            # のように社名本体が残ってしまう。
            # そこで、法人格のみ/末尾のみの検出は、隣接する社名本体までスパンを拡張する。
            corp_prefixes = ("株式会社", "有限会社", "合同会社", "合名会社", "合資会社")
            corp_abbr = ("(株)", "（株）")
            corp_suffixes = corp_prefixes
            # 境界（ここで社名の連結を止める）
            boundaries = set(
                " \t\r\n" +
                "、。,.，．:：;；()（）[]［］{}｛｝<>＜＞《》【】「」『』\"'“”‘’・/\\|?!？!"
            )

            def _expand_company_span(s: int, e: int) -> Tuple[int, int]:
                """Expand COMPANY span to cover adjacent company name tokens."""
                if s < 0 or e <= s or e > len(text):
                    return s, e
                seg = text[s:e]

                # 1) prefix-only (e.g., "株式会社") -> expand right
                if seg in corp_prefixes or seg in corp_abbr:
                    rr = e
                    # skip whitespace
                    while rr < len(text) and text[rr] in (" ", "\t", "\r", "\n"):
                        rr += 1
                    # consume name body until boundary
                    max_len = 80
                    consumed = 0
                    while rr < len(text) and text[rr] not in boundaries and consumed < max_len:
                        rr += 1
                        consumed += 1
                    return s, rr

                # 2) suffix-only (rare, e.g., "〇〇株式会社" broken and only suffix detected)
                if seg in corp_suffixes:
                    ll = s
                    while ll > 0 and text[ll - 1] in (" ", "\t", "\r", "\n"):
                        ll -= 1
                    max_len = 80
                    consumed = 0
                    while ll > 0 and text[ll - 1] not in boundaries and consumed < max_len:
                        ll -= 1
                        consumed += 1
                    return ll, e

                return s, e

            # apply expansion before slicing original
            if entity == "COMPANY" and r.get("source") != "forced":
                start, end = _expand_company_span(start, end)
                r["start"], r["end"] = start, end

            original = text[start:end]

            out.append(text[last:start])

            # decide replacement
            if r["source"] == "forced":
                if mode == "BLACK":
                    repl = BLACK_CHAR * max(
                        black_min_len, len(original)
                    )
                else:
                    label = r.get("label")
                    repl = (
                        label
                        if label
                        else state.get_label(
                            entity, original, label_format
                        )
                    )
                reason = r.get(
                    "forced_reason", "forced:mask_once"
                )
            else:
                if entity == "PARTIES":
                    repl = original
                    reason = "keep:parties"
                elif in_list(original, allowlist):
                    repl = original
                    reason = "keep:allowlist"
                elif entity == "MONEY" and not has_money_context(
                    text, start, end
                ):
                    repl = original
                    reason = "keep:money_no_context"
                else:
                    if mode == "BLACK":
                        repl = BLACK_CHAR * max(
                            black_min_len, len(original)
                        )
                        reason = "mask:black"
                    else:
                        if entity == "DATE":
                            repl = date_granular(
                                original, mode="YEAR"
                            )
                            reason = "mask:date_granular"
                        elif entity == "ADDRESS":
                            repl = mask_address_granular(
                                original,
                                addr_gran,
                                self.prefectures,
                                self.municipalities,
                            )
                            reason = "mask:address_granular"
                        else:
                            repl = state.get_label(
                                entity, original, label_format
                            )
                            reason = "mask:stable_id"

            out.append(repl)
            last = end

            hit = {
                "doc_id": doc_id,
                "entity_type": entity,
                "start": start,
                "end": end,
                "score": score,
                "original": original,
                "replacement": repl,
                "reason": reason,
                "source": r.get("source", "analyzer"),
            }
            hits.append(hit)

            if (
                (score and score < review_th)
                or reason in ("keep:money_no_context",)
                or r["source"] == "forced"
            ):
                h2 = dict(hit)
                h2["review_flag"] = True
                review.append(h2)

        out.append(text[last:])
        masked = "".join(out)

        report = {
            "doc_id": doc_id,
            "party_auto": {
                "self_names": party_result.self_names,
                "counter_names": party_result.counter_names,
            },
            "summary": {
                "total_hits": len(hits),
                "review_hits": len(review),
                "by_entity": _count_by_entity(hits),
            },
            "hits": hits,
            "review": review,
            "review_threshold": review_th,
            "runtime_overrides": {
                "once_allowlist": self.runtime.once_allowlist,
                "forced_masks": forced,
                "keep_spans": self.runtime.keep_spans,
            },
        }
        return masked, report
