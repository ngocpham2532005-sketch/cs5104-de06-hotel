#!/usr/bin/env python3
"""Dựng docs/BAO_CAO.pdf (A4) từ docs/BAO_CAO.md.

    pip install markdown playwright pypdf   # dùng Chrome có sẵn trên máy (channel="chrome"), không cần tải trình duyệt
    python docs/build_pdf.py

Dựng hai lượt: lượt 1 tìm trang của từng mục (pypdf), lượt 2 điền số trang vào mục lục (TOC1…TOC8).
"""
import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

DOCS = Path(__file__).resolve().parent
CSS = """
@page { size: A4; margin: 13mm 14mm 14mm 14mm; }
body { font-family: "Times New Roman", "Noto Serif", serif; font-size: 10.6pt; line-height: 1.36; color: #111; }
h1 { font-size: 17pt; margin: 4px 0 6px; line-height: 1.2; }
h2 { font-size: 13.5pt; margin: 14px 0 5px; border-bottom: 1px solid #999; padding-bottom: 1px; }
h3 { font-size: 11.8pt; margin: 9px 0 3px; }
p { margin: 3px 0 5px; text-align: justify; }
ul, ol { margin: 2px 0 5px; padding-left: 20px; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 4px 0 8px; font-size: 9.1pt; page-break-inside: avoid; }
th, td { border: 1px solid #aaa; padding: 2px 4px; vertical-align: top; }
th { background: #eef1f6; }
code { font-family: Menlo, Consolas, monospace; font-size: 8.8pt; background: #f4f4f4; padding: 0 2px; }
pre { background: #f4f4f4; padding: 5px 7px; font-size: 8.2pt; line-height: 1.25; page-break-inside: avoid; }
pre code { background: none; }
img { max-width: 100%; border: 1px solid #ccc; }
p > img[alt="Dashboard"] { width: 82%; display: block; margin: 0 auto; }
.two { display: flex; gap: 8px; } .two img { width: 50%; }
em { color: #333; }
blockquote { margin: 4px 0; padding: 3px 8px; border-left: 3px solid #c0521e; background: #fbf4ef; font-size: 9.3pt; }
.cover { text-align: center; border: 3px double #244a80; padding: 14mm 12mm 10mm; height: 266mm; box-sizing: border-box;
         display: flex; flex-direction: column; justify-content: space-between; break-after: page; }
.cover p { text-align: center; margin: 0; }
.cv-top { font-size: 13pt; line-height: 1.5; }
.cv-kind { font-size: 15pt; font-weight: bold; letter-spacing: 1px; margin-top: 18mm !important; }
.cv-course { font-size: 12.5pt; line-height: 1.5; }
.cv-title { font-size: 21pt; font-weight: bold; color: #244a80; }
.cv-sub { font-size: 14pt; font-style: italic; line-height: 1.45; }
table.cv-info { width: 82%; margin: 0 auto; font-size: 11.5pt; border: none; }
table.cv-info td { border: none; padding: 3px 6px; text-align: left; }
table.cv-info td:first-child { width: 30%; font-weight: bold; white-space: nowrap; }
table.cv-info code { font-size: 10pt; }
.cv-date { font-size: 12pt; font-style: italic; }
.toc { margin-bottom: 6px; }
.toc p { text-align: center; font-size: 12.5pt; margin: 0 0 4px; }
table.toc-t { font-size: 10pt; border: none; }
table.toc-t td { border: none; border-bottom: 1px dotted #999; padding: 2px 4px; }
table.toc-t td:first-child { font-weight: bold; white-space: nowrap; }
table.toc-t td:nth-child(2) { color: #444; font-size: 9pt; }
table.toc-t td:last-child { text-align: right; width: 4%; }
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


TOC = ["Tóm tắt", "1. Thiết kế phân tán", "2. Sơ đồ triển khai", "3. Nạp dữ liệu", "4. Cách chạy",
       "5. Kết quả và giải thích", "6. Phân công", "7. Tài liệu tham khảo"]


def render(body: str, out: Path):
    html = f"<!DOCTYPE html><html lang='vi'><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body}</body></html>"
    tmp = DOCS / "_bao_cao.html"
    tmp.write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        pg = b.new_page()
        pg.goto(tmp.as_uri())
        pg.wait_for_load_state("networkidle")
        pg.pdf(path=str(out), format="A4", print_background=True,
               display_header_footer=True, header_template="<span></span>",
               footer_template="<div style='font-size:8pt;width:100%;text-align:center;color:#666'>"
                               "CS5104 · Đề 6 · Nhóm 8 · <span class='pageNumber'></span>/<span class='totalPages'></span></div>",
               margin={"top": "15mm", "bottom": "16mm", "left": "18mm", "right": "15mm"})
        b.close()
    tmp.unlink()


def heading_pages(pdf: Path) -> list[str]:
    from pypdf import PdfReader
    pages = [" ".join(pg.extract_text().split()) for pg in PdfReader(str(pdf)).pages]
    found = []
    for title in TOC:
        # bỏ trang mục lục (trang 2 chứa mọi tiêu đề); lấy trang đầu tiên sau đó có tiêu đề
        n = next((i + 1 for i, txt in enumerate(pages) if i >= 1 and title in txt.replace(title, "", 1 if i == 1 else 0)), None)
        found.append(str(n) if n else "?")
    return found


def main():
    md = normalize((DOCS / "BAO_CAO.md").read_text(encoding="utf-8"))
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "md_in_html"])
    out = DOCS / "BAO_CAO.pdf"
    render(body, out)
    nums = heading_pages(out)
    for i, n in enumerate(nums, 1):
        body = body.replace(f"TOC{i}<", f"{n}<")
    render(body, out)
    print("-> docs/BAO_CAO.pdf · mục lục:", dict(zip(TOC, nums)))


if __name__ == "__main__":
    main()
