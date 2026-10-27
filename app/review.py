"""검수용 표시 (지시서 12절). 원문이 들어가므로 secure/review/ 에만 쓴다.
외부 글꼴·스크립트를 불러오지 않는 단일 HTML 파일이다."""
from __future__ import annotations

import csv
import html
from pathlib import Path

COLORS = {"label": "#ffd58a", "list": "#ffe9b8", "rule": "#b9e2ff", "ner": "#e3c8ff"}
SRC_KO = {"label": "라벨", "list": "명단", "rule": "규칙", "ner": "NER"}


def write(review_dir: Path, doc_id: str, text: str, masked: str, spans: list[dict], candidates: list[dict]):
    review_dir.mkdir(parents=True, exist_ok=True)
    with open(review_dir / f"{doc_id}.review.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["번호", "쪽", "줄", "시작", "끝", "종류", "출처", "원문", "치환값", "검수필요", "사유"])
        for i, s in enumerate(spans, 1):
            line = text.count("\n", 0, s["start"]) + 1
            w.writerow([i, 1, line, s["start"], s["end"], s["kind"], SRC_KO.get(s["source"], s["source"]),
                        s["orig"], s["repl"], "Y" if s["review"] else "N", s["reason"]])
        for c in candidates:
            line = text.count("\n", 0, c["start"]) + 1
            w.writerow(["후보", 1, line, c["start"], c["end"], c["kind"], "NER", c["word"], "", "Y",
                        f"후보(점수 {c['score']:.2f}, 가리지 않음)"])
    # 원문에 색 표시
    parts, pos = [], 0
    for i, s in enumerate(spans, 1):
        parts.append(html.escape(text[pos:s["start"]]))
        parts.append(f'<mark style="background:{COLORS.get(s["source"], "#ddd")}" title="{i} {s["kind"]} '
                     f'{SRC_KO.get(s["source"], "")}">{html.escape(text[s["start"]:s["end"]])}</mark>')
        pos = s["end"]
    parts.append(html.escape(text[pos:]))
    rows = "".join(
        f"<tr><td>{i}</td><td>{s['kind']}</td><td>{SRC_KO.get(s['source'], s['source'])}</td>"
        f"<td>{html.escape(s['orig'])}</td><td>{html.escape(s['repl'])}</td>"
        f"<td>{'Y' if s['review'] else ''}</td><td>{html.escape(s['reason'])}</td></tr>"
        for i, s in enumerate(spans, 1))
    rows += "".join(
        f"<tr><td>후보</td><td>{c['kind']}</td><td>NER</td><td>{html.escape(c['word'])}</td><td></td><td>Y</td>"
        f"<td>점수 {c['score']:.2f}, 가리지 않음</td></tr>" for c in candidates)
    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>검수 {doc_id}</title>
<style>body{{font-family:sans-serif;margin:16px;background:#fff;color:#111}}
.cols{{display:flex;gap:16px;flex-wrap:wrap}}.cols>div{{flex:1 1 420px;min-width:0}}
pre{{white-space:pre-wrap;word-break:break-all;border:1px solid #ccc;padding:8px;font-size:13px}}
table{{border-collapse:collapse;font-size:13px}}td,th{{border:1px solid #ccc;padding:3px 6px}}</style></head>
<body><h1>검수 {doc_id}</h1><p>노랑=라벨·명단, 파랑=규칙, 보라=NER</p>
<div class="cols"><div><h2>원문</h2><pre>{''.join(parts)}</pre></div>
<div><h2>가린 사본</h2><pre>{html.escape(masked)}</pre></div></div>
<h2>가린 위치</h2><table><tr><th>번호</th><th>종류</th><th>출처</th><th>원문</th><th>치환값</th><th>검수</th><th>사유</th></tr>
{rows}</table></body></html>"""
    (review_dir / f"{doc_id}.review.html").write_text(doc, encoding="utf-8")
