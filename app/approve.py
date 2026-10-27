"""검수를 마친 사본 승인 (pending/ → masked/).

- 누출 재검사에 실패한 문서는 승인하지 않는다.
- 검수 화면에서 남긴 "놓침" 표시가 있으면, 표시한 글자를 가린 사본 전체에서 찾아 모두 가린 뒤 승인한다.
  같은 이름이 여러 번 나와도 한 번만 표시하면 된다. 글자 사이 공백이 달라도 찾는다.
- "잘못 가림" 표시는 가린 채로 둔다. 더 가린 쪽이 안전하고, 다음 문서부터는 오답 노트가 반영한다.
- 화면과 로그에는 건수만 쓴다(값을 쓰지 않는다).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

TAG = {"RRN": "[주민번호]", "PHONE": "[전화번호]", "ADDR": "[주소]"}
DOC_ID = re.compile(r"^\d{8}-\d{3}$")


def _pattern(text: str) -> str:
    chars = [c for c in text if not c.isspace()]
    return r"\s*".join(re.escape(c) for c in chars)


def approve_doc(out_root: Path, doc_id: str) -> str:
    if not DOC_ID.match(doc_id):
        return "문서번호 형식이 아닙니다."
    src = out_root / "pending" / f"{doc_id}.md"
    mpf = out_root / "secure/maps" / f"{doc_id}.map.json"
    if not src.exists() or not mpf.exists():
        return f"{doc_id} 검수 대기 사본이 없습니다."
    mp = json.loads(mpf.read_text(encoding="utf-8"))
    if mp.get("recheck_leaks"):
        return f"{doc_id} 누출 재검사 실패 문서라 승인하지 않습니다."
    body = src.read_text(encoding="utf-8")
    head, sep, text = body.partition("\n---\n")   # 머리말(값 없음)은 건드리지 않는다
    if not sep:
        head, text = "", body
    mk = out_root / "secure/learn/marks" / f"{doc_id}.json"
    marks = json.loads(mk.read_text(encoding="utf-8")).get("marks", []) if mk.exists() else []
    misses = [m for m in marks if m.get("type") == "miss" and m.get("kind") in ("NAME", "RRN", "PHONE", "ADDR")]
    short = [m for m in misses if len(_pattern(m.get("text", "")).replace("\\s*", "")) < 2]
    if short:
        return (f"{doc_id} 놓침 표시 가운데 한 글자짜리가 {len(short)}개 있어 승인하지 않았습니다. "
                "표시를 지우고 두 글자 이상으로 다시 선택한 뒤 저장하세요.")
    used = [int(x) for x in re.findall(r"\[이름(\d+)\]", text)]
    nxt = max(used, default=0) + 1
    name_tag: dict[str, str] = {}
    added = 0
    # 긴 표시부터 바꾼다. 짧은 표시가 긴 값의 일부만 바꾸는 일을 막는다.
    for m in sorted(misses, key=lambda m: -len(m["text"])):
        key = "".join(c for c in m["text"] if not c.isspace())
        if m["kind"] == "NAME":
            if key not in name_tag:
                name_tag[key] = f"[이름{nxt}]"
                nxt += 1
            tag = name_tag[key]
        else:
            tag = TAG[m["kind"]]
        text, n = re.subn(_pattern(m["text"]), tag, text)
        added += n
    left = sum(len(re.findall(_pattern(m["text"]), text)) for m in misses)
    if left:
        return f"{doc_id} 표시한 값이 {left}곳 남아 승인하지 않았습니다."
    out = (head + sep if sep else "") + text
    out = out.replace("review: pending", "review: approved", 1)
    dst = out_root / "masked"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / f"{doc_id}.md").write_text(out, encoding="utf-8")
    msg = f"{doc_id} 승인 완료 → masked/"
    if misses:
        msg += f" (놓침 표시 {len(misses)}개를 적용해 {added}곳을 더 가렸습니다)"
    return msg


def is_approved(out_root: Path, doc_id: str) -> bool:
    return (out_root / "masked" / f"{doc_id}.md").exists()
