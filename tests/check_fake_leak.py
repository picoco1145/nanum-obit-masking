"""가짜화 결과를 정답표와 따로 대조하는 독립 검사(학습 실험용).

fakeify.check는 처리 단계가 찾은 값만 알고 검사한다. 이 스크립트는 정답표(tests/fake2/answers)에 적힌
진짜 값 전부를 기준으로 learn 폴더(회귀 사례·수정 요청·수정안·보고)에 원래 값이 남았는지 찾는다.
결과에는 진짜 값을 출력하지 않고 파일 이름·항목 종류·검사 방식만 적는다.

  .venv/bin/python tests/check_fake_leak.py LEARN_DIR [--fake-dir tests/fake2] [--docs N01,N02,...]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import fakeify  # noqa: E402


def digit_runs(s: str) -> str:
    out = []
    for c in s:
        if c.isdigit() or c in fakeify.KDIGIT:
            out.append(fakeify.KDIGIT.get(c, c))
        elif c.isspace() or c in "-–—.()*\\":
            continue
        else:
            out.append("|")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("learn_dir")
    ap.add_argument("--fake-dir", default=str(ROOT / "tests/fake2"))
    ap.add_argument("--docs", default=None)
    ap.add_argument("--out", default=None, help="표시를 남긴 실행 폴더. 주면 사례·요청을 자기 문서의 값과도 따로 대조한다")
    a = ap.parse_args()
    own = {}
    if a.out:
        for mf in (Path(a.out) / "secure/maps").glob("*.map.json"):
            mp = json.loads(mf.read_text(encoding="utf-8"))
            own[mp["doc_id"]] = mp["original_filename"][:3]
    ld = Path(a.learn_dir)
    docs = a.docs.split(",") if a.docs else None
    vals = []
    for p in sorted((Path(a.fake_dir) / "answers").glob("*.answer.json")):
        ans = json.loads(p.read_text(encoding="utf-8"))
        if docs and ans["doc"] not in docs:
            continue
        for it in ans["items"]:
            for v in [it["value"]] + list(it.get("forms") or []) + list(it.get("keys") or []):
                vals.append((ans["doc"], it["type"], v))
    files = [p for p in ld.rglob("*") if p.is_file() and p.suffix in (".json", ".yaml", ".md", ".jsonl")]
    bad = 0
    for p in files:
        raw = p.read_text(encoding="utf-8")
        try:
            t = json.dumps(json.loads(raw), ensure_ascii=False) if p.suffix == ".json" else raw
            t = json.loads(json.dumps(t))  # 이스케이프를 풀어 둔다
        except Exception:
            t = raw
        t = t.encode().decode("unicode_escape", errors="ignore") if "\\u" in t else t
        # 프로그램이 붙인 식별자(사례·요청 번호, 학습 상태 지문, 기록 시각)는 값이 아니므로 빼고 본다
        t = re.sub(r"\b[cq]-[0-9a-f]{8}\b|\b[0-9a-f]{12}\b|\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+\-]\d\d:\d\d", " ", t)
        tn = re.sub(r"\s+", "", t)
        mine = None
        try:
            js = json.loads(raw)
            if isinstance(js, dict):
                did = js.get("doc_id")
                if not did and js.get("case_id"):
                    cp = ld / "regress/cases" / f"{js['case_id']}.json"
                    did = json.loads(cp.read_text(encoding="utf-8")).get("doc_id") if cp.exists() else None
                mine = own.get(did)
        except Exception:
            pass
        td = digit_runs(t)
        for doc, typ, v in vals:
            how = None
            vn = re.sub(r"\s+", "", v)
            if typ == "NAME":
                hs = "".join(c for c in vn if fakeify.is_hangul(c) or fakeify.is_hanja(c))
                if len(hs) >= 2 and hs in tn:
                    how = "이름 전체"
                for w in re.findall(r"[A-Za-z]{3,}", v):
                    if re.search(re.escape(w), t, re.I):
                        how = "라틴 이름 낱말"
            elif typ in ("RRN", "PHONE"):
                d = digit_runs(v).replace("|", "")
                m = fakeify.PHONE_PREFIX_RX.match(d) if typ == "PHONE" else None
                body = d[len(m.group(0)):] if m else d
                if any(body[j:j + 4] in td for j in range(len(body) - 3)):
                    how = "숫자 4자리"
            elif typ == "ADDR":
                for w in re.findall(r"[A-Za-z]{3,}", v):
                    if w.lower() not in fakeify.EN_KEEP and re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", t, re.I):
                        how = "라틴 지명 낱말"
                for tok in re.findall(r"[가-힣]{2,}", v):
                    suf = next((x for x in fakeify.ADDR_SUFFIX if tok.endswith(x) and len(tok) > len(x)), "")
                    core = tok[:len(tok) - len(suf)] if suf else tok
                    if not fakeify.SIDO_RX.match(tok) and len(core) >= 2 and core in tn:
                        how = "지명 핵심어"
            if how:
                bad += 1
                same = "자기 문서" if mine == doc else ("다른 문서" if mine else "공용 파일")
                print(f"남음: {p.relative_to(ld)} | {doc} {typ} | {how} | {same}")
    print(f"검사한 파일 {len(files)}개, 정답 값 {len(vals)}개, 남은 값 {bad}건")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
