#!/usr/bin/env python3
"""Dựng docs/BAO_CAO.pdf (A4) từ docs/BAO_CAO.md.

    pip install markdown playwright      # dùng Chrome có sẵn trên máy (channel="chrome"), không cần tải trình duyệt
    python docs/build_pdf.py
"""
import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
CSS = """
@page { size: A4; margin: 13mm 14mm 14mm 14mm; }
body { font-family: "Times New Roman", "Noto Serif", serif; font-size: 10.3pt; line-height: 1.32; color: #111; }
h1 { font-size: 17pt; margin: 4px 0 6px; line-height: 1.2; }
h2 { font-size: 12.5pt; margin: 12px 0 4px; border-bottom: 1px solid #999; padding-bottom: 1px; }
h3 { font-size: 11pt; margin: 8px 0 3px; }
p { margin: 3px 0 5px; text-align: justify; }
ul, ol { margin: 2px 0 5px; padding-left: 20px; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 7px; font-size: 8.8pt; page-break-inside: avoid; }
th, td { border: 1px solid #aaa; padding: 2px 4px; vertical-align: top; }
th { background: #eef1f6; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.4pt; background: #f4f4f4; padding: 0 2px; }
pre { background: #f4f4f4; padding: 5px 7px; font-size: 8.2pt; line-height: 1.25; page-break-inside: avoid; }
pre code { background: none; }
img { max-width: 100%; border: 1px solid #ccc; }
p > img[alt="Dashboard"] { width: 82%; display: block; margin: 0 auto; }
.two { display: flex; gap: 8px; } .two img { width: 50%; }
em { color: #333; }
blockquote { margin: 4px 0; padding: 3px 8px; border-left: 3px solid #c0521e; background: #fbf4ef; font-size: 9.3pt; }
.cover { text-align: center; border: 1.5px solid #244a80; padding: 8px 10px 4px; margin-bottom: 8px; }
.cover p { text-align: center; margin: 2px 0; }
svg { page-break-inside: avoid; }
p:has(+ table), h3:has(+ table), p:has(+ p > img) { break-after: avoid; }
h2, h3 { break-after: avoid; }
"""


LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s")


def normalize(md: str) -> str:
    """Python-Markdown cần dòng trống trước danh sách và thụt 4 dấu cách cho danh sách lồng."""
    out, prev = [], ""
    for line in md.splitlines():
        m = LIST.match(line)
        if m:
            indent = len(m.group(1))
            line = " " * (indent * 2) + line.lstrip() if indent else line
            if prev.strip() and not LIST.match(prev) and not prev.startswith(" "):
                out.append("")
        out.append(line)
        prev = line
    return "\n".join(out)


def main():
    md = normalize((DOCS / "BAO_CAO.md").read_text(encoding="utf-8"))
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "md_in_html"])
    html = f"<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    tmp = DOCS / "_bao_cao.html"
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page()
        pg.goto(tmp.as_uri())
        pg.wait_for_load_state("networkidle")
        pg.pdf(path=str(DOCS / "BAO_CAO.pdf"), format="A4", print_background=True,
               display_header_footer=True, header_template="<span></span>",
               footer_template="<div style='font-size:8pt;width:100%;text-align:center;color:#666'>"
                               "CS5104 · Đề 6 · <span class='pageNumber'></span>/<span class='totalPages'></span></div>",
               margin={"top": "13mm", "bottom": "15mm", "left": "14mm", "right": "14mm"})
        b.close()
    tmp.unlink()
    print("-> docs/BAO_CAO.pdf")


if __name__ == "__main__":
    main()
