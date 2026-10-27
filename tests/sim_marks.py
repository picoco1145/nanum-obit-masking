"""학습 실험용: 직원이 검수 화면에서 남겼을 표시를 L 절반(N01·N02·N04·N05·N06)에 대신 기록한다.

검수 화면(mask.py review)이 저장하는 것과 같은 형식으로 <out>/secure/learn/marks/<문서번호>.json에 쓴다.
  .venv/bin/python tests/sim_marks.py tests/out/<실행이름>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# (파일 이름 앞부분, 표시 종류, 항목, 찾을 글, 그 안에서 표시할 부분)
MARKS = [
    ("N01", "over", "NAME", "변사자", None),
    ("N02", "miss", "NAME", "3.봉달례한자는", "봉달례"),
    ("N02", "miss", "NAME", "나몸사회복지사", "나몸"),
    ("N02", "miss", "NAME", "의료사회복자사표은서천학", "표은서"),
    ("N02", "miss", "PHONE", "공일공철실팔말구구공공", None),
    ("N02", "miss", "ADDR", "매구광여시기온구말빛 9길 14", None),
    ("N04", "miss", "NAME", "NGUYEN THI LAN", None),
    ("N04", "miss", "NAME", "王小明", None),
    ("N04", "miss", "ADDR", "12, Haesol-ro 3-gil, Garam-gu, Busan", None),
    ("N04", "over", "NAME", "가람수산", None),
    ("N05", "miss", "NAME", "여동생석미란", "석미란"),
    ("N06", "over", "NAME", "수신", None),
    ("N06", "over", "NAME", "방인", None),
]


def main():
    out = Path(sys.argv[1]).resolve()
    dest = out / "secure/learn/marks"
    dest.mkdir(parents=True, exist_ok=True)
    for mf in sorted((out / "secure/maps").glob("*.map.json")):
        mp = json.loads(mf.read_text(encoding="utf-8"))
        did, fn = mp["doc_id"], mp["original_filename"]
        text = (out / "secure/work" / f"{did}.md").read_text(encoding="utf-8")
        recs = mp["spans"]
        marks = []
        for pre, typ, kind, needle, part in MARKS:
            if not fn.startswith(pre):
                continue
            pos = 0
            n = 0
            while (i := text.find(needle, pos)) >= 0:
                pos = i + 1
                s = i + (needle.index(part) if part else 0)
                e = s + len(part or needle)
                hit = any(r["start"] < e and s < r["end"] for r in recs)
                full = all(text[k].isspace() or any(r["start"] <= k < r["end"] for r in recs) for k in range(s, e))
                if (typ == "over" and hit) or (typ == "miss" and not full):
                    marks.append({"type": typ, "kind": kind, "start": s, "end": e, "text": text[s:e]})
                    n += 1
            if n == 0:
                print(f"경고: {fn}에서 표시할 자리를 못 찾음({typ} {kind})")
        if marks:
            (dest / f"{did}.json").write_text(json.dumps({"doc_id": did, "saved": "sim_marks", "marks": marks},
                                                         ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{did} {fn}: 놓침 {sum(m['type'] == 'miss' for m in marks)}, "
                  f"잘못 가림 {sum(m['type'] == 'over' for m in marks)}")


if __name__ == "__main__":
    main()
