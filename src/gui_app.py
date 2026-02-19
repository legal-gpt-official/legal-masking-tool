"""Legal Masking v1.0 - GUI

Layout:
  - Left panel : Detection list (toggle + action buttons + search/filter)
  - Center     : Original text (read-only, highlight)
  - Right      : Masked preview (synced scroll)
  - Bottom     : Log panel (LogBus)
  - Toolbar    : Open / Run / Re-run / Manual Add / View Mode / Save / Report / Disclaimer

Features added/fixed vs previous version:
  - BUG FIX: _offset_from_index moved to class method (was nested in wrong scope)
  - BUG FIX: self.masked_text / self.report initialised in __init__
  - KEEP_ONCE / MASK_ONCE / ALWAYS_KEEP / ALWAYS_MASK_AS_COMPANY action buttons
  - Re-run button (once_allowlist / forced_masks reflected)
  - LogBus queue + log panel for progress
  - Right-click context menu: select range → choose entity → mask
  - Policy update integration (ALWAYS_* writes to YAML/dict + audit)
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, Menu

from app_controller import AppController
from engine.masking_engine import MaskingEngine, BLACK_CHAR
from report.report_exporter import export_html_side_by_side
from report.ui_payload import load_json, build_review_payload, save_json
from policy.policy_update import apply_user_actions
from policy.audit_log import append_audit_log
from log_bus import LogBus


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)


DISCLAIMER_LONG = (
    "【Legal Masking Tool 免責事項】\n\n"
    "本ソフトウェアは、文書中の情報抽出およびマスキング作業を支援するツールです。\n"
    "抽出・判定・置換の結果は完全性・正確性を保証しません。\n"
    "提出・開示等の最終判断は利用者の責任において行い、必ず目視で最終確認してください。\n\n"
    "開発・提供: Legal GPT編集部\n"
    "公式サイト: Legal-gpt.com"
)


# ---------------------------------------------------------------------------
# UI models
# ---------------------------------------------------------------------------


@dataclass
class Detection:
    id: int
    span_id: str
    mark_id: str
    entity_type: str
    start: int
    end: int
    original: str
    score: float
    reason: str
    source: str
    enabled: bool = True
    mask_override: Optional[str] = None
    is_review: bool = False


_ENTITY_ICON = {
    "PERSON": "👤", "NAME": "👤",
    "COMPANY": "🏢", "ORG": "🏢",
    "ADDRESS": "🏠", "LOCATION": "🏠",
    "EMAIL": "📧", "PHONE": "📞",
    "ID": "🆔", "DATE": "📅",
    "MONEY": "💰", "CUSTOM": "🏷️",
    "KEYWORD": "🔑",
}


def _icon_for(entity: str) -> str:
    return _ENTITY_ICON.get((entity or "").upper(), "🔎")


def _short(s: str, n: int = 28) -> str:
    s = (s or "").replace("\n", " ").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


# ---------------------------------------------------------------------------
# Detection list item widget
# ---------------------------------------------------------------------------


class DetectionListItem(ctk.CTkFrame):
    def __init__(
        self,
        master,
        detection: Detection,
        on_toggle,
        on_select,
        on_edit,
        on_hover,
        on_leave,
        on_action,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.d = detection
        self.on_toggle = on_toggle
        self.on_select = on_select
        self.on_edit = on_edit
        self.on_hover = on_hover
        self.on_leave = on_leave
        self.on_action = on_action

        self.configure(fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        # -- info area --
        info = ctk.CTkFrame(self, fg_color="transparent")
        info.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=6)
        title = f"{_icon_for(detection.entity_type)} {detection.entity_type}"
        if detection.is_review:
            title += "  ⚠"
        self.lbl_t = ctk.CTkLabel(
            info, text=title, font=("", 11, "bold"),
            anchor="w", text_color="#1a237e",
        )
        self.lbl_t.pack(fill="x")

        disp = _short(detection.original, 32)
        if detection.mask_override:
            disp += f" → {_short(detection.mask_override, 20)}"
        self.lbl_v = ctk.CTkLabel(
            info, text=disp, font=("", 11),
            anchor="w", text_color="#546e7a",
        )
        self.lbl_v.pack(fill="x")

        # -- action buttons + toggle --
        act = ctk.CTkFrame(self, fg_color="transparent")
        act.grid(row=0, column=1, sticky="nse", padx=(5, 10), pady=6)

        ctk.CTkButton(
            act, text="✎", width=28, height=24,
            command=lambda: self.on_edit(self.d),
            fg_color="#cfd8dc", text_color="#1a237e", hover_color="#b0bec5",
        ).pack(side="left", padx=1)

        self.sw = ctk.CTkSwitch(
            act, text="", width=40,
            command=self._toggle,
            progress_color="#1a237e",
        )
        self.sw.pack(side="left", padx=2)
        if self.d.enabled:
            self.sw.select()

        # -- action buttons row --
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 4))

        btn_style = dict(height=22, font=("", 9), corner_radius=4)
        ctk.CTkButton(
            btn_row, text="残す(今回)", width=68,
            command=lambda: self.on_action(self.d, "KEEP_ONCE"),
            fg_color="#e8f5e9", text_color="#2e7d32", hover_color="#c8e6c9",
            **btn_style,
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            btn_row, text="消す(今回)", width=68,
            command=lambda: self.on_action(self.d, "MASK_ONCE"),
            fg_color="#fce4ec", text_color="#c62828", hover_color="#f8bbd0",
            **btn_style,
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            btn_row, text="常に残す", width=62,
            command=lambda: self.on_action(self.d, "ALWAYS_KEEP"),
            fg_color="#e0f2f1", text_color="#00695c", hover_color="#b2dfdb",
            **btn_style,
        ).pack(side="left", padx=1)
        ctk.CTkButton(
            btn_row, text="常にCO.マスク", width=82,
            command=lambda: self.on_action(self.d, "ALWAYS_MASK_AS_COMPANY"),
            fg_color="#fff3e0", text_color="#e65100", hover_color="#ffe0b2",
            **btn_style,
        ).pack(side="left", padx=1)

        # -- separator --
        ctk.CTkFrame(self, height=1, fg_color="#e0e0e0").grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )

        # click / hover bindings
        for w in (self, info, self.lbl_t, self.lbl_v):
            w.bind("<Button-1>", lambda e: self.on_select(self.d.id))
            w.bind("<Enter>", lambda e: self.on_hover(self.d.id))
            w.bind("<Leave>", lambda e: self.on_leave())

    def _toggle(self):
        self.d.enabled = bool(self.sw.get())
        self.on_toggle()

    def set_highlight(self, active: bool):
        self.configure(fg_color="#e3f2fd" if active else "transparent")


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------


class MaskingApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Legal Masking Tool v1.0 — Legal GPT編集部")
        self.geometry("1440x920")

        try:
            icon_path = os.path.join(BASE_DIR, "favicon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        # -- LogBus --
        self.log_bus = LogBus()

        # -- backend --
        self.policy_path = os.path.join(BASE_DIR, "resources", "masking_policy.yaml")
        self.log_bus.emit("loading engine...")
        try:
            self.engine = MaskingEngine(self.policy_path, base_dir=BASE_DIR, log_fn=self.log_bus.emit)
            if not self.engine.nlp_available:
                self.log_bus.emit("WARNING: NLP not loaded. Using regex-only mode.")
                messagebox.showwarning(
                    "NLP Warning",
                    "NLP engine (GiNZA) could not be loaded.\n\n"
                    "The tool will work in regex-only mode\n"
                    "(lower accuracy but functional).\n\n"
                    "For full accuracy, run from Python:\n"
                    "  pip install ja-ginza\n"
                    "  python main.py",
                )
        except Exception as init_err:
            self.log_bus.emit(f"ENGINE INIT ERROR: {init_err}")
            messagebox.showerror(
                "Engine Error",
                f"Engine failed to initialize:\n\n{init_err}",
            )
            self.engine = None
        self.controller = AppController(BASE_DIR, self.engine, log_fn=self.log_bus.emit)
        self.log_bus.emit("engine ready")

        # -- state --
        self.current_file: Optional[str] = None
        self.original_text: str = ""
        self.masked_text: str = ""
        self.report: Dict[str, Any] = {}
        self.payload: Optional[Dict[str, Any]] = None
        self.last_result = None

        self.use_blackout: bool = False
        self.show_review_only: bool = True
        self.search_query: str = ""

        self.detections: List[Detection] = []
        self.det_items: Dict[int, DetectionListItem] = {}

        self._create_ui()

        # start log bus polling
        self._poll_log_bus()

    # ======================================================================
    # UI construction
    # ======================================================================

    def _create_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)  # log panel
        self.grid_rowconfigure(3, weight=0)  # status bar

        # -- toolbar --
        toolbar = ctk.CTkFrame(self, height=60, fg_color="#f5f5f5", corner_radius=0)
        toolbar.grid(row=0, column=0, sticky="ew")

        ctk.CTkButton(
            toolbar, text="📂 文書を開く", command=self._open_file,
            fg_color="#1a237e", hover_color="#0d47a1", width=120,
        ).pack(side="left", padx=15, pady=10)

        ctk.CTkButton(
            toolbar, text="▶ 解析", command=self._run,
            fg_color="#546e7a", width=90,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            toolbar, text="🔄 再解析", command=self._rerun,
            fg_color="#37474f", width=90,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            toolbar, text="➕ 手動追加", command=self._manual_add,
            fg_color="#546e7a", width=100,
        ).pack(side="left", padx=5)

        self.mask_menu = ctk.CTkOptionMenu(
            toolbar, values=["タグ形式 [種別]", "黒塗り ███"],
            command=self._change_mask, width=160,
            fg_color="#ffffff", text_color="#1a237e", button_color="#eceff1",
        )
        self.mask_menu.pack(side="left", padx=20)

        ctk.CTkButton(
            toolbar, text="🧾 レポート", command=self._open_report,
            fg_color="#2b2b2b", hover_color="#1f1f1f", width=100,
        ).pack(side="right", padx=10)

        ctk.CTkButton(
            toolbar, text="💾 確定保存", command=self._save,
            fg_color="#2e7d32", hover_color="#1b5e20", width=100,
        ).pack(side="right", padx=10)

        ctk.CTkButton(
            toolbar, text="⚖ 免責",
            command=lambda: messagebox.showinfo("免責", DISCLAIMER_LONG),
            width=70, fg_color="transparent", text_color="#546e7a",
        ).pack(side="right", padx=5)

        # -- main content area --
        main = ctk.CTkFrame(self, fg_color="#ffffff", corner_radius=0)
        main.grid(row=1, column=0, sticky="nsew", padx=10, pady=(10, 2))
        main.grid_columnconfigure(0, weight=0, minsize=380)
        main.grid_columnconfigure(1, weight=1)
        main.grid_columnconfigure(2, weight=1)
        main.grid_rowconfigure(0, weight=1)

        # -- left panel (search + toggle + list) --
        left = ctk.CTkFrame(main, fg_color="#fafafa", border_width=1, border_color="#e0e0e0")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(left, placeholder_text="検索（例: COMPANY / 甲 / 住所）")
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_search())

        self.view_switch = ctk.CTkSegmentedButton(
            left, values=["要確認", "全件"], command=self._change_view,
        )
        self.view_switch.set("要確認")
        self.view_switch.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        self.scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.scroll.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)

        # -- text areas --
        font_name = ("Consolas", 13) if sys.platform == "win32" else ("", 13)

        self.o_text = ctk.CTkTextbox(
            main, font=font_name, wrap="word",
            border_width=1, border_color="#e0e0e0",
        )
        self.o_text.grid(row=0, column=1, sticky="nsew", padx=4)

        self.m_text = ctk.CTkTextbox(
            main, font=font_name, wrap="word",
            border_width=1, border_color="#e0e0e0",
        )
        self.m_text.grid(row=0, column=2, sticky="nsew", padx=4)

        # -- context menu for right-click add --
        self.context_menu = Menu(self, tearoff=0, font=("", 10))
        self._ctx_range: Optional[Tuple[int, int, str]] = None
        self._bind_context_menu(self.o_text, self._show_context_menu)

        # -- scroll sync --
        self.o_text._textbox.configure(yscrollcommand=self._sync_scroll_o)
        self.m_text._textbox.configure(yscrollcommand=self._sync_scroll_m)

        # -- masked hover highlight --
        self.m_text.tag_config("highlight", underline=True)
        self.m_text._textbox.bind("<Motion>", self._masked_hover)
        self.m_text._textbox.bind("<Leave>", lambda e: self._leave_all())

        # -- log panel --
        log_frame = ctk.CTkFrame(self, height=100, fg_color="#fafafa", corner_radius=0)
        log_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 2))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame, text="📋 ログ", font=("", 10, "bold"),
            text_color="#546e7a", anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(4, 0))

        self.log_text = ctk.CTkTextbox(
            log_frame, height=80, font=("", 10), wrap="word",
            fg_color="#ffffff", border_width=1, border_color="#e0e0e0",
        )
        self.log_text.grid(row=1, column=0, sticky="ew", padx=10, pady=(2, 6))

        # -- status bar --
        status = ctk.CTkFrame(self, height=30, fg_color="#eeeeee", corner_radius=0)
        status.grid(row=3, column=0, sticky="ew")
        self.status_left = ctk.CTkLabel(
            status, text="status: ready", font=("", 10), text_color="#546e7a",
        )
        self.status_left.pack(side="left", padx=15)
        self.status_right = ctk.CTkLabel(
            status, text="", font=("", 10), text_color="#1a237e",
        )
        self.status_right.pack(side="right", padx=20)

    # ======================================================================
    # Log bus polling
    # ======================================================================

    def _poll_log_bus(self):
        msgs = self.log_bus.drain()
        if msgs:
            for m in msgs:
                self.log_text.insert("end", m + "\n")
            self.log_text.see("end")
        self.after(150, self._poll_log_bus)

    # ======================================================================
    # Offset utilities (BUG FIX: now a proper class method)
    # ======================================================================

    def _offset_from_index(self, index: str) -> int:
        """Convert a Tk text index ('line.char') to a character offset from '1.0'."""
        try:
            count = self.o_text._textbox.count("1.0", index, "chars")
            if count is None:
                return 0
            if isinstance(count, (list, tuple)):
                return int(count[0])
            return int(count)
        except Exception:
            # fallback: parse 'line.col' manually
            try:
                parts = str(index).split(".")
                line = int(parts[0])
                col = int(parts[1]) if len(parts) > 1 else 0
                text = self.original_text or ""
                lines = text.split("\n")
                offset = sum(len(lines[i]) + 1 for i in range(min(line - 1, len(lines))))
                return offset + col
            except Exception:
                return 0

    # ======================================================================
    # Actions
    # ======================================================================

    def _set_status(self, s: str):
        self.status_left.configure(text=f"status: {s}")

    def _open_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("文書", "*.docx *.pdf *.txt"), ("All", "*.*")],
        )
        if not p:
            return
        self.current_file = p
        self._set_status(f"selected: {os.path.basename(p)}")
        self.status_right.configure(text="")
        self.log_bus.emit(f"file selected: {os.path.basename(p)}")

    def _open_report(self):
        if not self.last_result or not self.original_text:
            messagebox.showinfo("info", "先に「解析」を実行してください")
            return
        try:
            # GUI状態から直接レポートを生成（手動追加を確実に反映）
            self._export_report_from_gui_state(self.last_result.out_report_html)
            self.log_bus.emit("report regenerated from GUI state")
        except Exception as e:
            messagebox.showerror("error", f"レポート生成に失敗しました: {e}")
            return

        webbrowser.open(f"file://{os.path.abspath(self.last_result.out_report_html)}")

    def _change_mask(self, v: str):
        self.use_blackout = ("黒塗り" in (v or ""))
        self._render_texts()

    def _change_view(self, v: str):
        self.show_review_only = (v == "要確認")
        self._refresh_list()

    def _on_search(self):
        self.search_query = (self.search_entry.get() or "").strip()
        self._refresh_list()

    # ======================================================================
    # Build detections from payload
    # ======================================================================

    def _build_detections_from_payload(self, payload: Dict[str, Any]) -> List[Detection]:
        spans = payload.get("spans", []) or []
        review_ids = set(x.get("span_id") for x in (payload.get("review_items") or []))
        dets: List[Detection] = []
        for idx, s in enumerate(spans, start=1):
            dets.append(
                Detection(
                    id=idx,
                    span_id=str(s.get("span_id")),
                    mark_id=str(s.get("mark_id")),
                    entity_type=str(s.get("entity_type") or "UNKNOWN"),
                    start=int(s.get("start")),
                    end=int(s.get("end")),
                    original=str(s.get("original") or ""),
                    score=float(s.get("score") or 0.0),
                    reason=str(s.get("reason") or ""),
                    source=str(s.get("source") or "analyzer"),
                    enabled=True,
                    mask_override=None,
                    is_review=(s.get("span_id") in review_ids),
                )
            )
        dets.sort(key=lambda d: d.start)
        for i, d in enumerate(dets, start=1):
            d.id = i
        return dets

    # ======================================================================
    # Run / Re-run
    # ======================================================================

    def _run(self):
        if not self.current_file:
            messagebox.showinfo("info", "ファイルを選択してください")
            return
        self._execute(fresh=True)

    def _rerun(self):
        """再解析: 現在のGUI設定を反映してプレビューを更新。"""
        if not self.current_file:
            messagebox.showinfo("info", "ファイルを選択してください")
            return
        if not self.original_text:
            messagebox.showinfo("info", "先に「解析」を実行してください")
            return
        self._execute(fresh=False)

    def _execute(self, fresh: bool = True):
        if self.engine is None:
            messagebox.showerror(
                "Engine Error",
                "NLP engine is not loaded.\nPlease check ja-ginza installation.",
            )
            return

        def worker():
            try:
                self.after(0, lambda: self._set_status("processing..."))
                self.log_bus.emit("=== start processing ===")

                # reflect mask mode
                self.engine.policy.setdefault("output", {})
                self.engine.policy["output"]["mode"] = "BLACK" if self.use_blackout else "LABEL"

                # runtime overrides from current UI
                once_allowlist, forced_masks, keep_spans = self._collect_runtime_overrides()
                self.engine.set_runtime_overrides(
                    once_allowlist=once_allowlist,
                    forced_masks=forced_masks,
                    keep_spans=keep_spans,
                )
                self.log_bus.emit(
                    f"overrides: allow={len(once_allowlist)} forced={len(forced_masks)} keep={len(keep_spans)}"
                )

                if fresh:
                    res = self.controller.process_file(self.current_file)
                    payload = load_json(res.out_payload_json)
                else:
                    # re-run: use stored original_text, re-analyze
                    self.log_bus.emit("re-analyzing with current overrides...")
                    masked_text, report = self.engine.mask_text_with_report(
                        self.original_text,
                        doc_id=os.path.basename(self.current_file or "doc"),
                    )
                    report["original_text_used"] = self.original_text
                    report["masked_text_generated"] = masked_text

                    # re-export report/payload
                    if self.last_result:
                        export_html_side_by_side(
                            original_text=self.original_text,
                            masked_text=masked_text,
                            report=report,
                            out_html_path=self.last_result.out_report_html,
                        )
                        payload = build_review_payload(
                            doc_id=os.path.basename(self.current_file or "doc"),
                            original_text=self.original_text,
                            masked_text=masked_text,
                            report=report,
                        )
                        save_json(self.last_result.out_payload_json, payload)
                        res = self.last_result
                        res.masked_text = masked_text
                        res.report = report
                    else:
                        res = None
                        payload = build_review_payload(
                            doc_id="doc",
                            original_text=self.original_text,
                            masked_text=masked_text,
                            report=report,
                        )

                def apply():
                    if res is not None:
                        self.last_result = res
                        self.original_text = res.original_text
                    self.payload = payload
                    self.masked_text = payload.get("masked_text", "")
                    self.report = {}
                    self.detections = self._build_detections_from_payload(payload)
                    total = payload.get("summary", {}).get("total_hits", 0)
                    rev = payload.get("summary", {}).get("review_hits", 0)
                    self.status_right.configure(text=f"hits={total} / review={rev}")
                    self._render_texts()
                    self._refresh_list()
                    self._set_status(f"解析完了（{total}件検出, {rev}件要確認）— 編集後「確定保存」で出力")
                    self.log_bus.emit(f"解析完了: {total} hits, {rev} review items")

                self.after(0, apply)
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: self._set_status("error"))
                self.after(0, lambda m=err_msg: messagebox.showerror("error", m))
                self.log_bus.emit(f"ERROR: {err_msg}")

        threading.Thread(target=worker, daemon=True).start()

    def _save(self):
        """確定保存: GUI上の編集結果を反映したファイルを、保存先を選んで出力する。"""
        if not self.current_file:
            messagebox.showinfo("info", "ファイルを選択してください")
            return
        if not self.original_text:
            messagebox.showinfo("info", "先に「解析」を実行してください")
            return

        ext = os.path.splitext(self.current_file)[1].lower()
        base = os.path.basename(self.current_file)
        default_name = f"masked_{base}"

        if ext == ".docx":
            ftypes = [("Word文書", "*.docx"), ("全ファイル", "*.*")]
        elif ext == ".pdf":
            ftypes = [("PDF", "*.pdf"), ("全ファイル", "*.*")]
        else:
            ftypes = [("テキスト", "*.txt"), ("全ファイル", "*.*")]

        save_path = filedialog.asksaveasfilename(
            defaultextension=ext,
            initialfile=default_name,
            filetypes=ftypes,
            title="マスキング済みファイルの保存先",
        )
        if not save_path:
            return

        def worker():
            import shutil
            try:
                self.after(0, lambda: self._set_status("確定出力中..."))
                self.log_bus.emit("=== 確定保存開始 ===")

                # 1) エンジンにGUI上の編集状態を反映
                self.engine.policy.setdefault("output", {})
                self.engine.policy["output"]["mode"] = "BLACK" if self.use_blackout else "LABEL"

                once_allowlist, forced_masks, keep_spans = self._collect_runtime_overrides()
                self.engine.set_runtime_overrides(
                    once_allowlist=once_allowlist,
                    forced_masks=forced_masks,
                    keep_spans=keep_spans,
                )
                self.log_bus.emit(
                    f"  overrides: allow={len(once_allowlist)} forced={len(forced_masks)} keep={len(keep_spans)}"
                )

                # 2) パイプライン再実行 → output/ に仮出力
                #    (解析結果のサマリ/警告収集のため。DOCXの確定出力はGUI状態から作る)
                self.log_bus.emit("  pipeline running...")
                res = self.controller.process_file(self.current_file)

                # 3) マスキング済みファイルを保存先へ出力
                if ext == ".docx":
                    # GUI上で手動追加したマスクも含め、画面の確定状態をそのままDOCXへ反映する
                    self._export_docx_from_gui_state(self.current_file, save_path)
                    self.log_bus.emit(f"  masked file (GUI state) → {save_path}")

                    # output/ 側の masked もGUI状態で上書きして同期（exe配布後の一貫性向上）
                    try:
                        self._export_docx_from_gui_state(self.current_file, res.out_masked_path)
                        self.log_bus.emit(f"  masked file (sync output/) → {res.out_masked_path}")
                    except Exception as _e:
                        self.log_bus.emit(f"  WARNING: output/ masked sync skipped: {_e}")
                else:
                    shutil.copy2(res.out_masked_path, save_path)
                    self.log_bus.emit(f"  masked file → {save_path}")

                # 4) HTMLレポート・CSVを保存先と同じフォルダに出力
                save_dir = os.path.dirname(os.path.abspath(save_path))
                save_base = os.path.basename(save_path)
                report_html_path = os.path.join(save_dir, f"report_{save_base}.html")
                csv_out_path = os.path.join(save_dir, f"hits_{save_base}.csv")

                # HTMLレポートはGUI状態から直接生成（手動追加を確実に反映）
                self._export_report_from_gui_state(report_html_path)
                self.log_bus.emit(f"  report → {report_html_path}")

                # CSVもGUI状態から書き出す（手動追加/KEEP変更を確実に反映）
                try:
                    import csv as _csv
                    dets = sorted([d for d in self.detections if d.enabled], key=lambda d: d.start)
                    with open(csv_out_path, "w", encoding="utf-8-sig", newline="") as f:
                        w = _csv.writer(f)
                        w.writerow(["entity_type", "start", "end", "original", "replacement", "score", "reason", "source"])
                        for d in dets:
                            w.writerow([
                                d.entity_type, int(d.start), int(d.end),
                                d.original, self._replacement_for(d),
                                float(d.score or 0.0), d.reason, d.source
                            ])
                    self.log_bus.emit(f"  CSV (GUI state) → {csv_out_path}")

                    # output/ 側のCSVも同期（存在すれば上書き）
                    try:
                        shutil.copy2(csv_out_path, res.out_csv_path)
                    except Exception:
                        pass
                except Exception as e:
                    # フォールバック: パイプライン出力をコピー
                    if os.path.exists(res.out_csv_path):
                        shutil.copy2(res.out_csv_path, csv_out_path)
                        self.log_bus.emit(f"  CSV → {csv_out_path}")
                    else:
                        self.log_bus.emit(f"  CSV export skipped: {e}")

                # output/ 内のレポートも同期更新
                self._export_report_from_gui_state(res.out_report_html)

                abs_save = os.path.abspath(save_path)
                abs_report = os.path.abspath(report_html_path)
                abs_csv = os.path.abspath(csv_out_path)

                def done():
                    self.last_result = res
                    self._set_status(f"確定保存完了: {os.path.basename(save_path)}")
                    self.log_bus.emit("=== 確定保存完了 ===")
                    messagebox.showinfo(
                        "確定保存完了",
                        f"マスキング済みファイル:\n  {abs_save}\n\n"
                        f"レポート (HTML):\n  {abs_report}\n\n"
                        f"検出一覧 (CSV):\n  {abs_csv}",
                    )

                self.after(0, done)
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: self._set_status("保存エラー"))
                self.after(0, lambda m=err_msg: messagebox.showerror("error", m))
                self.log_bus.emit(f"ERROR: {err_msg}")

        threading.Thread(target=worker, daemon=True).start()

    def _export_report_from_gui_state(self, out_html_path: str) -> None:
        """GUI上の検出状態からHTMLレポートを生成する。

        エンジン再実行ではなく self.detections を直接参照するため、
        手動追加やKEEP/MASKの変更が確実に反映される。
        """
        txt = self.original_text or ""
        dets = sorted(
            [d for d in self.detections if d.enabled],
            key=lambda d: d.start,
        )
        hits: List[Dict[str, Any]] = []
        parts: List[str] = []
        cur = 0
        for d in dets:
            if d.start < cur:
                continue
            parts.append(txt[cur:d.start])
            repl = self._replacement_for(d)
            parts.append(repl)
            hits.append({
                "start": d.start, "end": d.end,
                "entity_type": d.entity_type,
                "original": d.original, "replacement": repl,
                "score": d.score, "reason": d.reason, "source": d.source,
            })
            cur = d.end
        parts.append(txt[cur:])
        masked_text = "".join(parts)

        warnings = []
        if self.last_result and self.last_result.report:
            warnings.extend(self.last_result.report.get("docx_warnings", []) or [])
            warnings.extend(self.last_result.report.get("pdf_warnings", []) or [])

        report = {
            "hits": hits,
            "review": [
                h for h in hits
                if float(h.get("score", 0) or 0) < 0.8
                or h.get("source") == "forced"
            ],
            "summary": {
                "total_hits": len(hits),
                "review_hits": len([d for d in self.detections if d.is_review and d.enabled]),
            },
            "docx_warnings": [w for w in warnings if "docx" in w or "track" in w],
            "pdf_warnings": [w for w in warnings if "pdf" in w],
        }
        export_html_side_by_side(
            original_text=txt,
            masked_text=masked_text,
            report=report,
            out_html_path=out_html_path,
        )

    def _export_docx_from_gui_state(self, src_docx_path: str, out_docx_path: str) -> None:
        """GUI上の検出状態（self.detections）を使ってDOCXを書き出す。

        engine を再実行すると、(1) NLP/regexモード差分、(2) 解析結果の揺れ により
        GUIで手動追加したマスクが落ちることがある。
        ここでは self.detections（=画面上で確定したマスク/KEEP状態）を単一の真実として扱い、
        docx_segments のセグメントマップに対して置換を適用して保存する。
        """
        from pipelines.docx_segments import extract_docx_segments
        from pipelines.docx_pipeline import map_hit_to_segments, _piece_replacement
        from pipelines.docx_rewrite import rewrite_docx_with_maps

        original_text, segments, docx_warnings = extract_docx_segments(src_docx_path)

        # 念のため、GUIが保持している元テキストと差がある場合はログに残す（差分があると座標がズレる）
        if (self.original_text or "") and (self.original_text != original_text):
            self.log_bus.emit("WARNING: original_text mismatch between GUI and DOCX extraction. Export may be inaccurate.")

        dets = sorted([d for d in self.detections if d.enabled], key=lambda d: d.start)

        # GUIの置換文字列を使って hits を構築（reportと同じロジック）
        hits = []
        for d in dets:
            hits.append({
                "start": int(d.start),
                "end": int(d.end),
                "entity_type": d.entity_type,
                "original": d.original,
                "replacement": self._replacement_for(d),
                "reason": d.reason,
                "source": d.source,
            })

        docx_maps = []
        for h in hits:
            maps = map_hit_to_segments(h, segments)
            if not maps:
                continue
            repl = h.get("replacement", "")
            for m in maps:
                piece_len = int(m["local_end"]) - int(m["local_start"])
                docx_maps.append({
                    "seg_id": m["seg_id"],
                    "local_start": int(m["local_start"]),
                    "local_end": int(m["local_end"]),
                    "replacement": _piece_replacement(repl, piece_len),
                })

        rewrite_docx_with_maps(src_docx_path, out_docx_path, docx_maps)

    # ======================================================================
    # Runtime overrides
    # ======================================================================

    def _collect_runtime_overrides(
        self,
    ) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, int]]]:
        keep_spans = [
            {"start": d.start, "end": d.end}
            for d in self.detections
            if not d.enabled
        ]
        forced_masks: List[Dict[str, Any]] = []
        for d in self.detections:
            if not d.enabled:
                continue
            if d.source == "forced" or d.mask_override:
                forced_masks.append({
                    "start": d.start,
                    "end": d.end,
                    "entity_type": d.entity_type,
                    "label": d.mask_override,
                    "reason": "forced:ui_override" if d.mask_override else "forced:manual_add",
                })
        once_allowlist: List[str] = []
        return once_allowlist, forced_masks, keep_spans

    # ======================================================================
    # Detection actions (KEEP_ONCE / MASK_ONCE / ALWAYS_KEEP / ALWAYS_MASK_AS_COMPANY)
    # ======================================================================

    def _on_detection_action(self, d: Detection, action: str):
        audit_path = os.path.join(BASE_DIR, "audit_log.jsonl")

        if action == "KEEP_ONCE":
            d.enabled = False
            self.log_bus.emit(f"KEEP_ONCE: {_short(d.original, 20)}")
            append_audit_log(audit_path, {
                "action": "KEEP_ONCE",
                "entity_type": d.entity_type,
                "original": d.original,
                "start": d.start, "end": d.end,
            })

        elif action == "MASK_ONCE":
            d.enabled = True
            d.source = "forced"
            self.log_bus.emit(f"MASK_ONCE: {_short(d.original, 20)}")
            append_audit_log(audit_path, {
                "action": "MASK_ONCE",
                "entity_type": d.entity_type,
                "original": d.original,
                "start": d.start, "end": d.end,
            })

        elif action == "ALWAYS_KEEP":
            d.enabled = False
            # YAML allowlist に永続追加
            try:
                result = apply_user_actions(
                    policy_yaml_path=self.policy_path,
                    spans=[{
                        "span_id": d.span_id,
                        "original": d.original,
                        "entity_type": d.entity_type,
                        "start": d.start, "end": d.end,
                    }],
                    user_actions={
                        "doc_id": os.path.basename(self.current_file or "doc"),
                        "actions": [{"span_id": d.span_id, "op": "ALWAYS_KEEP"}],
                    },
                    custom_companies_path=os.path.join(
                        BASE_DIR, "resources", "dict", "custom_companies.txt"
                    ),
                    audit_log_path=audit_path,
                )
                self.log_bus.emit(
                    f"ALWAYS_KEEP: '{_short(d.original, 20)}' → YAML allowlist updated"
                )
                # reload policy in engine
                from engine.policy import load_policy
                self.engine.policy = load_policy(self.policy_path)
            except Exception as e:
                self.log_bus.emit(f"ALWAYS_KEEP error: {e}")
                messagebox.showerror("error", f"ALWAYS_KEEP 失敗: {e}")

        elif action == "ALWAYS_MASK_AS_COMPANY":
            d.enabled = True
            d.entity_type = "COMPANY"
            d.source = "forced"
            try:
                result = apply_user_actions(
                    policy_yaml_path=self.policy_path,
                    spans=[{
                        "span_id": d.span_id,
                        "original": d.original,
                        "entity_type": d.entity_type,
                        "start": d.start, "end": d.end,
                    }],
                    user_actions={
                        "doc_id": os.path.basename(self.current_file or "doc"),
                        "actions": [{"span_id": d.span_id, "op": "ALWAYS_MASK_AS_COMPANY"}],
                    },
                    custom_companies_path=os.path.join(
                        BASE_DIR, "resources", "dict", "custom_companies.txt"
                    ),
                    audit_log_path=audit_path,
                )
                self.log_bus.emit(
                    f"ALWAYS_MASK_AS_COMPANY: '{_short(d.original, 20)}' → dict updated"
                )
            except Exception as e:
                self.log_bus.emit(f"ALWAYS_MASK_AS_COMPANY error: {e}")
                messagebox.showerror("error", f"ALWAYS_MASK_AS_COMPANY 失敗: {e}")

        self._render_texts()
        self._refresh_list(keep_scroll=True)

    # ======================================================================
    # Edit detection
    # ======================================================================

    def _edit_detection(self, d: Detection):
        if not d:
            return
        val = simpledialog.askstring(
            "置換文字の編集",
            "置換したい文字（空欄で解除）",
            initialvalue=d.mask_override or "",
        )
        if val is None:
            return
        val = val.strip()
        d.mask_override = val if val else None
        d.enabled = True
        self._render_texts()
        self._refresh_list(keep_scroll=True)

    def _toggle_changed(self):
        self._render_texts()

    # ======================================================================
    # Manual add
    # ======================================================================

    def _manual_add(self):
        if not self.original_text:
            messagebox.showinfo("info", "先に実行して原文を読み込んでください")
            return
        sel = self._get_selected_original()
        if not sel:
            messagebox.showinfo("info", "原文から範囲選択してください")
            return
        entity = simpledialog.askstring(
            "手動追加",
            "エンティティ種別（例: PERSON / COMPANY / ADDRESS / ID / EMAIL / PHONE / DATE / MONEY / CUSTOM）",
            initialvalue="CUSTOM",
        )
        if not entity:
            return
        self._quick_add(sel, entity.strip().upper())

    # ======================================================================
    # Right-click context menu
    # ======================================================================

    def _bind_context_menu(self, ctk_textbox, handler):
        def _try_bind(widget, sequence):
            try:
                widget.bind(sequence, handler, add="+")
            except Exception:
                pass

        targets = []
        if ctk_textbox is not None:
            targets.append(ctk_textbox)
            inner = getattr(ctk_textbox, "_textbox", None)
            if inner is not None:
                targets.append(inner)

        sequences = [
            "<Button-3>",
            "<Control-Button-1>",
        ]
        for t in targets:
            for seq in sequences:
                _try_bind(t, seq)

    def _show_context_menu(self, event):
        """Show context menu. If nothing is selected, auto-select token around cursor."""
        try:
            sel = self._get_selected_original()
            if sel:
                try:
                    idx_s = self._offset_from_index(self.o_text._textbox.index("sel.first"))
                    idx_e = self._offset_from_index(self.o_text._textbox.index("sel.last"))
                except Exception:
                    idx_s, idx_e = 0, 0
            else:
                idx_s, idx_e, sel = self._select_token_at(event)

            sel = (sel or "").strip()
            if not sel or idx_e <= idx_s:
                return

            self._ctx_range = (idx_s, idx_e, sel)

            self.context_menu.delete(0, "end")
            categories = [
                ("👤 氏名", "PERSON"),
                ("🏢 法人名", "COMPANY"),
                ("🏠 住所", "ADDRESS"),
                ("🆔 ID/番号", "ID"),
                ("📧 メール", "EMAIL"),
                ("📞 電話", "PHONE"),
                ("📅 日付", "DATE"),
                ("💰 金額", "MONEY"),
                ("🏷️ 任意", "CUSTOM"),
            ]
            for lbl, ent in categories:
                self.context_menu.add_command(
                    label=lbl,
                    command=lambda e=ent: self._quick_add_range(e),
                )
            self.context_menu.add_separator()
            self.context_menu.add_command(label="➕ 詳細設定…", command=self._manual_add)
            # tk_popup handles focus/grab correctly on Windows
            # (post requires an extra click to activate the menu)
            self.context_menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            return

    def _get_selected_original(self) -> str:
        try:
            return self.o_text.get("sel.first", "sel.last")
        except Exception:
            return ""

    def _select_token_at(self, event) -> Tuple[int, int, str]:
        """Auto-select a token-like range around the cursor in original text."""
        try:
            idx = self.o_text._textbox.index(f"@{event.x},{event.y}")
        except Exception:
            return (0, 0, "")

        try:
            pos = self._offset_from_index(idx)
        except Exception:
            pos = 0

        txt = self.original_text or ""
        if not txt:
            return (0, 0, "")

        pos = max(0, min(pos, len(txt) - 1))
        stop_chars = set(
            " \t\r\n　,，.。．、:：;；()（）[]【】{}「」『』<>＜＞\"'""''|｜/／\\\\'・"
        )

        s = pos
        e = pos

        if s < len(txt) and txt[s] in stop_chars and s > 0:
            s -= 1
            e = s

        while s > 0 and txt[s - 1] not in stop_chars and (pos - s) < 80:
            s -= 1
        while e < len(txt) and txt[e] not in stop_chars and (e - pos) < 80:
            e += 1

        token = txt[s:e].strip()
        if not token:
            return (0, 0, "")

        # reflect selection in textbox
        try:
            self.o_text._textbox.tag_remove("sel", "1.0", "end")
            self.o_text._textbox.tag_add("sel", f"1.0 + {s}c", f"1.0 + {e}c")
        except Exception:
            pass
        return (s, e, token)

    def _quick_add_range(self, entity: str):
        """Add forced masking using last context range (set by context menu)."""
        if not self._ctx_range:
            sel = self._get_selected_original()
            if not sel:
                return
            try:
                s = self._offset_from_index(self.o_text._textbox.index("sel.first"))
                e = self._offset_from_index(self.o_text._textbox.index("sel.last"))
            except Exception:
                return
            self._quick_add_with_range(s, e, sel, entity)
            return
        s, e, sel = self._ctx_range
        self._quick_add_with_range(int(s), int(e), sel, entity)

    def _quick_add(self, sel: str, entity: str):
        """Backward compatible entry point (used by manual add)."""
        try:
            s = self._offset_from_index(self.o_text._textbox.index("sel.first"))
            e = self._offset_from_index(self.o_text._textbox.index("sel.last"))
        except Exception:
            return
        self._quick_add_with_range(s, e, sel, entity)

    def _quick_add_with_range(self, idx_s: int, idx_e: int, sel: str, entity: str):
        """Core add. Validates offsets match selected text; relocates near if not."""
        if idx_e <= idx_s:
            return
        txt = self.original_text or ""
        sel0 = (sel or "").strip()
        if not sel0:
            return

        # validate
        ok = False
        if 0 <= idx_s <= len(txt) and 0 <= idx_e <= len(txt):
            if txt[idx_s:idx_e] == sel:
                ok = True
            elif txt[idx_s:idx_s + len(sel)] == sel:
                idx_e = idx_s + len(sel)
                ok = True

        if not ok:
            win_l = max(0, idx_s - 200)
            win_r = min(len(txt), idx_s + 200 + len(sel))
            found = txt.find(sel, win_l, win_r)
            if found != -1:
                idx_s = found
                idx_e = found + len(sel)
                ok = True

        if not ok:
            found = txt.find(sel)
            if found != -1:
                idx_s = found
                idx_e = found + len(sel)

        # COMPANY: expand to include adjacent corporate designators
        if entity.upper() == "COMPANY":
            left_terms = ["株式会社", "有限会社", "合同会社", "（株）", "(株)", "㈱"]
            for t in left_terms:
                if txt[max(0, idx_s - len(t)):idx_s] == t:
                    idx_s -= len(t)
                    sel0 = (t + sel0).strip()
                    break
            right_terms = ["株式会社", "有限会社", "合同会社"]
            for t in right_terms:
                if txt[idx_e:idx_e + len(t)] == t:
                    idx_e += len(t)
                    sel0 = (sel0 + t).strip()
                    break

        # avoid duplicate
        span_key = (entity.upper(), idx_s, idx_e)
        existing = next(
            (d for d in self.detections
             if (d.entity_type.upper(), d.start, d.end) == span_key and d.source == "forced"),
            None,
        )
        if existing:
            existing.enabled = True
            self._render_texts()
            self._refresh_list(keep_scroll=True)
            return

        new = Detection(
            id=999999,
            span_id=f"manual_{idx_s}_{idx_e}",
            mark_id=f"manual_{idx_s}_{idx_e}",
            entity_type=entity.upper(),
            start=int(idx_s),
            end=int(idx_e),
            original=txt[int(idx_s):int(idx_e)] if txt else sel0,
            score=1.0,
            reason="forced:manual_add",
            source="forced",
            enabled=True,
            mask_override=None,
            is_review=False,
        )
        self.detections.append(new)
        self.detections.sort(key=lambda d: (d.start, -d.end))
        for i, d in enumerate(self.detections, start=1):
            d.id = i
        self._render_texts()
        self._refresh_list(keep_scroll=True)
        self.log_bus.emit(f"manual add: {entity} '{_short(sel0, 20)}' [{idx_s}:{idx_e}]")

        # audit
        append_audit_log(
            os.path.join(BASE_DIR, "audit_log.jsonl"),
            {
                "action": "manual_add",
                "entity_type": entity,
                "original": sel0,
                "start": idx_s, "end": idx_e,
            },
        )

    # ======================================================================
    # Render
    # ======================================================================

    def _replacement_for(self, d: Detection) -> str:
        if d.mask_override and not self.use_blackout:
            return d.mask_override
        if self.use_blackout:
            return BLACK_CHAR * max(3, len(d.original))
        return f"[{d.entity_type}]"

    def _render_texts(self):
        self.o_text.delete("1.0", "end")
        self.o_text.insert("1.0", self.original_text or "")

        # build masked with tags per detection
        self.m_text.delete("1.0", "end")
        self.m_text.tag_remove("highlight", "1.0", "end")
        for tag in list(self.m_text.tag_names()):
            if tag.startswith("det_"):
                self.m_text.tag_delete(tag)

        txt = self.original_text or ""
        dets = [d for d in self.detections if d.enabled]
        dets.sort(key=lambda d: d.start)

        cur = 0
        for d in dets:
            if d.start < cur:
                continue
            self.m_text.insert("end", txt[cur:d.start])
            repl = self._replacement_for(d)
            tag = f"det_{d.id}"
            start_idx = self.m_text.index("end")
            self.m_text.insert("end", repl)
            end_idx = self.m_text.index("end")
            self.m_text.tag_add(tag, start_idx, end_idx)
            cur = d.end
        self.m_text.insert("end", txt[cur:])

        # reset original highlight
        self.o_text.tag_delete("selected")
        self.o_text.tag_config("selected", underline=True)

    def _filtered_detections(self) -> List[Detection]:
        dets = self.detections
        if self.show_review_only:
            dets = [d for d in dets if d.is_review]
        q = (self.search_query or "").strip().lower()
        if q:
            dets = [
                d for d in dets
                if q in (d.entity_type or "").lower()
                or q in (d.original or "").lower()
                or q in (d.reason or "").lower()
            ]
        return dets

    def _refresh_list(self, keep_scroll: bool = False):
        y = None
        if keep_scroll:
            try:
                y = self.scroll._parent_canvas.yview()[0]
            except Exception:
                y = None

        for w in self.scroll.winfo_children():
            w.destroy()
        self.det_items = {}

        dets = self._filtered_detections()
        if not dets:
            ctk.CTkLabel(
                self.scroll, text="該当なし", text_color="#546e7a",
            ).pack(anchor="w", padx=10, pady=10)
        else:
            for d in dets:
                item = DetectionListItem(
                    self.scroll,
                    detection=d,
                    on_toggle=self._toggle_changed,
                    on_select=self._select_detection,
                    on_edit=self._edit_detection,
                    on_hover=self._hover_from_list,
                    on_leave=self._leave_all,
                    on_action=self._on_detection_action,
                )
                item.pack(fill="x", padx=0, pady=0)
                self.det_items[d.id] = item

        if y is not None:
            try:
                self.scroll._parent_canvas.yview_moveto(y)
            except Exception:
                pass

    # ======================================================================
    # Selection / highlight
    # ======================================================================

    def _select_detection(self, det_id: int):
        d = next((x for x in self.detections if x.id == det_id), None)
        if not d:
            return
        try:
            self.o_text.see(f"1.0 + {d.start}c")
            self.o_text.tag_remove("selected", "1.0", "end")
            self.o_text.tag_add("selected", f"1.0 + {d.start}c", f"1.0 + {d.end}c")
        except Exception:
            pass

        self._leave_all()
        try:
            self.m_text.tag_add("highlight", f"det_{det_id}.first", f"det_{det_id}.last")
        except Exception:
            pass
        if det_id in self.det_items:
            self.det_items[det_id].set_highlight(True)

    def _hover_from_list(self, det_id: int):
        try:
            self.m_text.tag_add("highlight", f"det_{det_id}.first", f"det_{det_id}.last")
        except Exception:
            pass
        if det_id in self.det_items:
            self.det_items[det_id].set_highlight(True)

    def _leave_all(self):
        self.m_text.tag_remove("highlight", "1.0", "end")
        for it in self.det_items.values():
            it.set_highlight(False)

    def _masked_hover(self, event):
        try:
            idx = self.m_text._textbox.index(f"@{event.x},{event.y}")
            tags = self.m_text._textbox.tag_names(idx)
            det_tags = [t for t in tags if t.startswith("det_")]
            if not det_tags:
                self._leave_all()
                return
            det_id = int(det_tags[0].split("_")[1])
            self._leave_all()
            self._hover_from_list(det_id)
        except Exception:
            return

    # ======================================================================
    # Scroll sync
    # ======================================================================

    def _sync_scroll_o(self, *args):
        try:
            self.m_text._textbox.yview_moveto(args[0])
            self.o_text._scrollbar.set(*args)
        except Exception:
            return

    def _sync_scroll_m(self, *args):
        try:
            self.o_text._textbox.yview_moveto(args[0])
            self.m_text._scrollbar.set(*args)
        except Exception:
            return


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_gui():
    app = MaskingApp()
    app.mainloop()
