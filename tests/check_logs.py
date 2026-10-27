"""화면 출력과 logs/ 폴더에 가짜 개인정보 값이 찍히지 않았는지, netguard 로그가 비었는지 확인한다.

python tests/check_logs.py results/run_all.log tests/out/*
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
vals = set()
for f in (ROOT / "tests/fake/answers").glob("*.answer.json"):
    a = json.loads(f.read_text(encoding="utf-8"))
    for it in a["items"]:
        if it["type"] == "NAME":
            vals.add(it["value"])
        elif it["type"] in ("RRN", "PHONE"):
            vals.add(re.sub(r"\D", "", it["value"])[:7])  # 숫자 앞 7자리
        elif it["type"] == "ADDR":
            vals.update(it["keys"])


def scan(path: Path) -> list[str]:
    t = path.read_text(encoding="utf-8", errors="replace")
    tn = re.sub(r"\s+", "", t)
    runs = [re.sub(r"\D", "", m.group(0)) for m in re.finditer(r"\d[\d\- .()*]{5,}\d", t)]
    hits = [v for v in vals if (v in tn if not v.isdigit() else any(v in r for r in runs))]
    return hits


bad = 0
for arg in sys.argv[1:]:
    p = Path(arg)
    files = [p] if p.is_file() else [x for x in (p / "logs").glob("*") if x.is_file()]
    for f in files:
        if f.name == "netguard.log":
            n = len(f.read_text(errors="replace").strip())
            print(f"{f}: netguard {'비어 있음' if n == 0 else f'{n}바이트 — 확인 필요'}")
            bad += n > 0
            continue
        h = scan(f)
        if h:
            bad += 1
            print(f"{f}: 가짜 값 {len(h)}종 발견")
    if p.is_dir() and not (p / "logs/netguard.log").exists():
        print(f"{p}: netguard.log 없음(외부 접속 시도 기록 없음)")
print("결과:", "이상 없음" if bad == 0 else f"확인 필요 {bad}건")
