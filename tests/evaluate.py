"""정답표와 가린 사본을 대조해 놓친 것(누출)과 잘못 가린 것(과잉)을 센다.

python tests/evaluate.py tests/out/<실행이름> [--name 이름] [--fake-dir tests/fake2]
결과: results/eval_<이름>.json 과 화면 요약
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANS = ROOT / "tests/fake/answers"
H = "가-힣"
KD = {"공": "0", "영": "0", "빵": "0", "일": "1", "이": "2", "삼": "3", "사": "4", "오": "5", "육": "6",
      "륙": "6", "칠": "7", "팔": "8", "구": "9"}
NUMRUN = re.compile(r"[0-9공영일이삼사오육칠팔구][0-9공영일이삼사오육칠팔구*\\\-–. ()]{5,}")
# 엄격 채점(--strict): 붙어 쓴 이름, 영문 O·l 오독 숫자, 글자가 틀어진 한글 숫자·주소도 놓침으로 센다
STRICT = False
KD_LATIN = {"O": "0", "o": "0", "l": "1", "I": "1", "|": "1"}
NUMRUN_STRICT = re.compile(r"[0-9공영일이삼사오육칠팔구Ol][0-9공영일이삼사오육칠팔구Ol*\\\-–. ()]{5,}")


def fmt_of(fname: str) -> str:
    for k in ("text", "hwpx", "scan", "fax"):
        if f"_{k}." in fname:
            return k
    return "?"


def body(md: str) -> str:
    if md.startswith("---\n"):
        return md.split("\n---\n", 1)[1]
    return md


def name_pat(form: str) -> str:
    chars = [c for c in form if not c.isspace()]
    core = r"[ \t]*".join(re.escape(c) for c in chars)
    left = rf"(?:(?<![{H}])|(?<=[고망故]))"
    if STRICT and len(chars) >= 3:
        left = ""          # OCR이 띄어쓰기를 지워 앞 낱말에 붙은 이름(여동생석미란)도 센다
    if len(chars) <= 2 and " " not in form:
        return rf"{left}{core}(?=[^{H}]|$|[은는이가을를의에께와과도만님씨군양으])"
    return rf"{left}{core}"


def fuzzy_pats(value: str) -> list[str]:
    out = []
    if len(value) < 3:
        return out
    for i in range(len(value)):
        p = "".join((rf"(?!{re.escape(c)})[{H}]" if j == i else re.escape(c)) for j, c in enumerate(value))
        out.append(rf"(?<![{H}]){p}")
    return out


def digits_of(s: str) -> str:
    kd = {**KD, **KD_LATIN} if STRICT else KD
    return "".join(kd.get(c, c) for c in s if c.isdigit() or c in kd)


def grams(d: str, n: int = 7) -> set[str]:
    return {d[i:i + n] for i in range(len(d) - n + 1)}


def num_runs(text: str) -> list[tuple[int, str, str]]:
    out = []
    for m in (NUMRUN_STRICT if STRICT else NUMRUN).finditer(text):
        d = digits_of(m.group(0))
        if len(d) >= 7:
            out.append((m.start(), m.group(0), d))
    return out


def is_subseq(d: str, a: str) -> bool:
    it = iter(a)
    return all(c in it for c in d)


def count_num(text: str, value: str, ocr: bool = False, skip: tuple = ()) -> list[str]:
    a = re.sub(r"\D", "", digits_of(value))
    out = []
    for _, raw, d in num_runs(text):
        if any(re.sub(r"\D", "", k) and re.sub(r"\D", "", k) in d for k in skip):
            continue   # 가리면 안 되는 값(사업자번호 등)은 누출로 세지 않는다
        if a in d or (len(d) >= 7 and d in a):
            out.append(raw)
        elif ocr and len(d) == len(a) and sum(x != y for x, y in zip(d, a)) <= 1:
            out.append(raw + "(OCR변형)")
        elif ocr and len(a) >= 9 and len(d) >= 7 and (grams(d, 7) & grams(a, 7) or (d[:3] == a[:3] and d[-4:] == a[-4:])
                                                       or (len(d) >= 0.6 * len(a) and is_subseq(d, a))):
            # OCR이 숫자 몇 개를 빠뜨리거나 바꾼 번호: 7자리 연속 일치, 앞 3자리와 끝 4자리 일치, 순서대로 60% 이상 남음
            out.append(raw + "(OCR부분일치)")
    return out


def garbled_korean_digits(text: str, value_forms: list[str], value: str) -> list[str]:
    """한글 숫자로 쓴 번호가 OCR에서 몇 글자 틀어진 경우(공일공철실팔말…)를 찾는다(엄격 채점)."""
    if not any(any(c in KD for c in f) and sum(c in KD for c in f) >= 6 for f in value_forms):
        return []
    a = re.sub(r"\D", "", digits_of(value))
    out = []
    for m in re.finditer(rf"[{H}][{H} ]{{7,}}", text):
        run = m.group(0).replace(" ", "")
        for i in range(0, max(1, len(run) - len(a) + 1)):
            w = run[i:i + len(a)]
            if len(w) < len(a):
                break
            same = sum(1 for c, d in zip(w, a) if KD.get(c) == d)
            if same >= 0.7 * len(a):
                out.append(w + "(OCR한글숫자)")
                break
    return out


def addr_fuzzy2(t: str, key: str) -> list[str]:
    """주소 핵심어와 글자 2개 이내로 다른 구간(숫자는 모두 같아야 함)을 찾는다(엄격 채점)."""
    if len(key) < 6:
        return []
    kd = re.sub(r"\D", "", key)
    out = []
    for L in range(len(key) - 2, len(key) + 2):
        for i in range(0, len(t) - L + 1):
            w = t[i:i + L]
            if re.sub(r"\D", "", w) != kd:
                continue
            if lev(w, key) <= 2:
                out.append(w + "(OCR변형2)")
                return out
    return out


def nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def addr_hits(text: str, keys: list[str], fuzzy: bool) -> list[str]:
    t = nospace(text)
    hits = []
    for k in keys:
        n = t.count(k)
        hits += [k] * n
        if fuzzy and n == 0 and len(k) >= 5:
            before = len(hits)
            for i in range(len(k)):
                p = re.escape(k[:i]) + "." + re.escape(k[i + 1:])
                for m in re.finditer(p, t):
                    hits.append(m.group(0) + "(OCR변형)")
            if STRICT and len(hits) == before:
                hits += addr_fuzzy2(t, k)
    return hits


def eval_doc(mp: dict, raw: str, masked: str, ans: dict, fmt: str, src: str):
    ocr = fmt in ("scan", "fax")
    res = {"leaks": [], "ocr_lost": [], "over": [], "over_other": [], "ocr_variant_masked": []}
    for it in ans["items"]:
        t = it["type"]
        if t == "NAME":
            forms = it["forms"]
            in_r = sum(len(re.findall(name_pat(f), raw)) for f in forms)
            expected = sum(len(re.findall(name_pat(f), src)) for f in forms)
            seen_pos = set()
            for f in forms:
                for m in re.finditer(name_pat(f), masked):
                    if m.start() in seen_pos:
                        continue      # 표기 두 가지(띄어 씀/붙여 씀)가 같은 자리를 두 번 세지 않게 한다
                    seen_pos.add(m.start())
                    res["leaks"].append({"type": "NAME", "value": it["value"], "found": m.group(0), "how": "그대로",
                                         "role": it["role"], "ctx": masked[max(0, m.start() - 12):m.end() + 8]})
            if ocr:
                for p in fuzzy_pats(it["value"]):
                    for m in re.finditer(p, masked):
                        res["leaks"].append({"type": "NAME", "value": it["value"], "found": m.group(0),
                                             "how": "OCR 한 글자 변형", "role": it["role"],
                                             "ctx": masked[max(0, m.start() - 12):m.end() + 8]})
            if in_r < expected:
                res["ocr_lost"].append({"type": t, "value": it["value"], "expected": expected, "in_text": in_r})
        elif t in ("RRN", "PHONE"):
            vals = [it["value"]] + [f for f in it.get("forms", []) if f != it["value"]]
            seen = set()
            for v in vals:
                for raw_hit in count_num(masked, v, ocr, tuple(x for x in ans["must_not"] if len(re.sub(r"\D", "", x)) >= 7)):
                    if raw_hit in seen:
                        continue
                    seen.add(raw_hit)
                    res["leaks"].append({"type": t, "value": it["value"], "found": raw_hit, "how": "숫자 7자리 이상 일치",
                                         "role": it["role"], "ctx": ""})
            if STRICT and ocr:
                for g in garbled_korean_digits(masked, vals, it["value"]):
                    res["leaks"].append({"type": t, "value": it["value"], "found": g, "how": "한글 숫자 OCR 변형",
                                         "role": it["role"], "ctx": ""})
            in_r = len({r for v in vals for r in count_num(raw, v)})
            if in_r < it["count"]:
                res["ocr_lost"].append({"type": t, "value": it["value"], "expected": it["count"], "in_text": in_r})
        elif t == "ADDR":
            for h in addr_hits(masked, it["keys"], ocr):
                res["leaks"].append({"type": "ADDR", "value": it["value"], "found": h, "how": "주소 핵심어",
                                     "role": it["role"], "ctx": ""})
    # 정답에 없는 것을 가린 구간
    bad = []
    for sp in mp["spans"]:
        o = nospace(sp["orig"])
        mt = match_answer(o, sp["kind"], ans, ocr)
        if mt == "ocr":
            res["ocr_variant_masked"].append({"orig": sp["orig"], "kind": sp["kind"]})
        if not mt:
            res["over_other"].append({"orig": sp["orig"], "kind": sp["kind"], "source": sp["source"],
                                      "ctx": raw[max(0, sp["start"] - 10):sp["end"] + 6]})
            bad.append((sp["start"], sp["end"]))
    # 걸리면 안 되는 값: 정답이 아닌 구간에 들어가 가려진 경우만 센다
    for s in ans["must_not"] + ans.get("must_not_extra", []):
        for m in re.finditer(re.escape(s), raw):
            if any(a < m.end() and m.start() < b for a, b in bad):
                res["over"].append({"value": s, "ctx": raw[max(0, m.start() - 10):m.end() + 6]})
    return res


def lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_answer(o: str, kind: str, ans: dict, ocr: bool):
    """정답과 맞으면 "exact", OCR이 틀리게 읽은 정답 값이면 "ocr", 아니면 False."""
    od = re.sub(r"\D", "", digits_of(o)) if kind not in ("NAME",) else ""
    for it in ans["items"]:
        if it["type"] == "NAME":
            for f in it["forms"] + [it["value"]]:
                fn = nospace(f).replace("씨", "")
                if fn and (fn in o or o in nospace(f) or o in it["value"]):
                    return "exact"
            if len(o) == len(it["value"]) and sum(a != b for a, b in zip(o, it["value"])) <= 1:
                return "exact"
        elif it["type"] in ("RRN", "PHONE"):
            vals = [it["value"]] + it.get("forms", [])
            for v in vals:
                vd = digits_of(v)
                if od and len(od) >= 6 and (grams(od, 6) & grams(vd, 6)):
                    return "exact"
        elif it["type"] == "ADDR":
            for k in it["keys"]:
                if k in o or (len(o) >= 4 and o in nospace(it["value"])):
                    return "exact"
            if ocr and len(o) >= 5:
                v = nospace(it["value"])
                common = sum(1 for c in set(o) if c in v)
                if common >= 0.6 * len(set(o)):
                    return "exact"
    if not ocr:
        return False
    # OCR이 글자를 틀리게 읽은 정답 값: 이름은 편집 거리 1(4글자 이상은 2) 이내, 번호는 끝 4자리 일치
    for it in ans["items"]:
        if it["type"] == "NAME" and kind == "NAME" and len(o) >= 2:
            cands = {it["value"]} | {nospace(f) for f in it["forms"] if len(nospace(f)) >= 2}
            for c in cands:
                lim = 2 if len(c) >= 4 else 1
                if lev(o, c) <= lim and any(ch in c for ch in o):
                    return "ocr"
        elif it["type"] in ("RRN", "PHONE") and kind in ("RRN", "PHONE", "ORG_PHONE") and len(od) >= 7:
            for v in [it["value"]] + it.get("forms", []):
                vd = re.sub(r"\D", "", digits_of(v))
                if len(vd) >= 4 and od[-4:] == vd[-4:]:
                    return "ocr"
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--name", default=None)
    ap.add_argument("--strict", action="store_true", help="엄격 채점(붙은 이름·O/l 오독·틀어진 한글 숫자·주소)")
    ap.add_argument("--fake-dir", default=None, help="정답표·원본이 있는 가짜 세트 폴더(기본 tests/fake)")
    a = ap.parse_args()
    global ANS, STRICT
    STRICT = a.strict
    fake = Path(a.fake_dir).resolve() if a.fake_dir else ROOT / "tests/fake"
    ANS = fake / "answers"
    out = Path(a.out)
    name = a.name or out.name
    metrics = {}
    mpath = out / "logs/metrics.jsonl"
    if mpath.exists():
        for ln in mpath.read_text(encoding="utf-8").splitlines():
            m = json.loads(ln)
            metrics[m["doc_id"]] = m
    per = defaultdict(lambda: {"docs": 0, "leak": defaultdict(int), "over_must_not": 0, "over_other": 0,
                               "ocr_lost": 0, "recheck_fail": 0, "ocr_variant": 0, "cpu": [], "wall": [], "rss": []})
    details = []
    for mf in sorted((out / "secure/maps").glob("*.map.json")):
        mp = json.loads(mf.read_text(encoding="utf-8"))
        did = mp["doc_id"]
        fname = mp["original_filename"]
        fmt = fmt_of(fname)
        ans = json.loads((ANS / f"{fname[:3]}.answer.json").read_text(encoding="utf-8"))
        raw = (out / "secure/work" / f"{did}.md").read_text(encoding="utf-8")
        masked = body((out / "pending" / f"{did}.md").read_text(encoding="utf-8"))
        src = (fake / "src" / f"{fname[:3]}.md").read_text(encoding="utf-8")
        r = eval_doc(mp, raw, masked, ans, fmt, src)
        p = per[fmt]
        p["docs"] += 1
        for lk in r["leaks"]:
            p["leak"][lk["type"]] += 1
        p["over_must_not"] += len(r["over"])
        p["over_other"] += len(r["over_other"])
        p["ocr_lost"] += len(r["ocr_lost"])
        p["ocr_variant"] += len(r["ocr_variant_masked"])
        p["recheck_fail"] += 1 if mp.get("recheck_leaks") else 0
        if did in metrics:
            p["cpu"].append(metrics[did]["total_cpu_s"])
            p["wall"].append(metrics[did]["total_wall_s"])
            p["rss"].append(metrics[did]["max_rss_mb"])
        details.append({"doc": fname, "doc_id": did, "format": fmt, **r,
                        "metrics": metrics.get(did)})
    summary = {}
    for fmt, p in per.items():
        cpu_sorted = sorted(p["cpu"])
        summary[fmt] = {"docs": p["docs"], "leak": dict(p["leak"]), "leak_total": sum(p["leak"].values()),
                        "over_must_not": p["over_must_not"], "over_other": p["over_other"],
                        "ocr_lost": p["ocr_lost"], "recheck_fail": p["recheck_fail"],
                        "ocr_variant_masked": p["ocr_variant"],
                        # 첫 문서는 모델을 읽는 시간이 들어가므로 중앙값을 장당 시간으로 쓴다
                        "cpu_median_s": round(statistics.median(cpu_sorted), 2) if cpu_sorted else None,
                        "cpu_first_s": p["cpu"][0] if p["cpu"] else None,
                        "wall_median_s": round(statistics.median(p["wall"]), 2) if p["wall"] else None,
                        "max_rss_mb": max(p["rss"]) if p["rss"] else None}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"eval_{name}.json").write_text(
        json.dumps({"name": name, "summary": summary, "details": details}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"== {name}")
    for fmt in ("text", "hwpx", "scan", "fax"):
        if fmt in summary:
            s = summary[fmt]
            print(f"{fmt:5} 문서 {s['docs']} | 놓침 {s['leak_total']} {s['leak']} | 금지값가림 {s['over_must_not']} "
                  f"| 기타가림 {s['over_other']} | OCR변형가림 {s['ocr_variant_masked']} | OCR손실 {s['ocr_lost']} | 재검사실패 {s['recheck_fail']} "
                  f"| CPU중앙 {s['cpu_median_s']}s 첫장 {s['cpu_first_s']}s | RSS {s['max_rss_mb']}MB")


if __name__ == "__main__":
    main()
