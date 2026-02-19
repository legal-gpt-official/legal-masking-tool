from __future__ import annotations
import os
import html
from typing import Dict, Any, List


def _escape(s: str) -> str:
    return html.escape(s or "").replace("\n", "<br>")


def _inject_marks(
    original_text: str, hits: List[Dict[str, Any]]
) -> str:
    text = original_text
    items = []
    for idx, h in enumerate(hits, start=1):
        items.append(
            (int(h["start"]), int(h["end"]), f"m{idx:06d}")
        )
    for s, e, mid in sorted(
        items, key=lambda x: x[0], reverse=True
    ):
        frag = text[s:e]
        text = (
            text[:s]
            + f"[[[MARK:{mid}]]]"
            + frag
            + f"[[[/MARK:{mid}]]]"
            + text[e:]
        )
    esc = _escape(text)
    for _, _, mid in items:
        esc = esc.replace(
            f"[[[MARK:{mid}]]]",
            f'<mark id="{mid}" class="mk">',
        )
        esc = esc.replace(f"[[[/MARK:{mid}]]]", "</mark>")
    return esc


def export_html_side_by_side(
    original_text: str,
    masked_text: str,
    report: Dict[str, Any],
    out_html_path: str,
) -> None:
    hits = report.get("hits", [])

    left = _inject_marks(original_text, hits)
    right = _escape(masked_text)

    warnings = []
    warnings.extend(report.get("docx_warnings", []) or [])
    warnings.extend(report.get("pdf_warnings", []) or [])

    warn_html = ""
    if warnings:
        warn_html = (
            "<div class='warn'><b>Warnings:</b> "
            + " / ".join(html.escape(w) for w in warnings)
            + "</div>"
        )

    page = (
        '<!doctype html>\n'
        '<html lang="ja">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Masking Report</title>\n"
        "<style>\n"
        "body{font-family:system-ui, -apple-system, Segoe UI, Arial; margin:0;}\n"
        ".top{padding:10px 14px; border-bottom:1px solid #ddd; background:#fafafa;}\n"
        ".wrap{display:flex; height:calc(100vh - 62px);}\n"
        ".pane{flex:1; overflow:auto; padding:12px 14px; line-height:1.6;}\n"
        ".left{border-right:1px solid #eee; background:#fff;}\n"
        ".right{background:#fcfcff;}\n"
        ".mk{background: #fff2a8; padding:0 2px; cursor:pointer;}\n"
        ".warn{margin-top:8px; padding:8px 10px; background:#fff0f0; border:1px solid #ffcccc; border-radius:8px;}\n"
        "small{color:#666;}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        '<div class="top">\n'
        "  <div><b>Side-by-side Report</b> <small>(click highlight / synced scroll)</small></div>\n"
        f"  {warn_html}\n"
        "</div>\n"
        '<div class="wrap">\n'
        f'  <div id="left" class="pane left">{left}</div>\n'
        f'  <div id="right" class="pane right">{right}</div>\n'
        "</div>\n"
        "<script>\n"
        'const L = document.getElementById("left");\n'
        'const R = document.getElementById("right");\n'
        "let lock=false;\n"
        "function sync(a,b){\n"
        "  if(lock) return;\n"
        "  lock=true;\n"
        "  const ratio = a.scrollTop / (a.scrollHeight - a.clientHeight + 1);\n"
        "  b.scrollTop = ratio * (b.scrollHeight - b.clientHeight);\n"
        "  setTimeout(()=>lock=false, 10);\n"
        "}\n"
        'L.addEventListener("scroll", ()=>sync(L,R));\n'
        'R.addEventListener("scroll", ()=>sync(R,L));\n'
        'document.querySelectorAll("mark.mk").forEach(m=>{\n'
        '  m.addEventListener("click", ()=>{\n'
        '    m.scrollIntoView({block:"center"});\n'
        "    sync(L,R);\n"
        "  });\n"
        "});\n"
        "</script>\n"
        "</body>\n"
        "</html>\n"
    )
    os.makedirs(
        os.path.dirname(os.path.abspath(out_html_path)),
        exist_ok=True,
    )
    with open(out_html_path, "w", encoding="utf-8") as f:
        f.write(page)
