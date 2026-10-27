"""부고 공문 개인정보 마스킹 시제품 — 실행 진입점.

python app/mask.py run --inbox tests/fake --out tests/out/spec --profile spec
python app/mask.py approve <문서번호> [--out <폴더>]
python app/mask.py review [--out <폴더>]

로그와 화면에는 건수·상태만 남긴다(값을 출력하지 않는다).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
try:
    import resource
except ImportError:  # Windows에는 resource 모듈이 없다. 시간·메모리 측정만 0으로 남긴다
    resource = None
import shutil
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path.insert(0, str(APP))

import netguard  # noqa: E402

netguard.set_offline_env()
os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(ROOT / "models/paddlex"))

import yaml  # noqa: E402

import labels  # noqa: E402
import learnstate  # noqa: E402
import rules  # noqa: E402

KIND_TAG = {"RRN": "[주민번호]", "PHONE": "[전화번호]", "ORG_PHONE": "[기관전화]", "ADDR": "[주소]",
            "ORG_ADDR": "[기관주소]"}
PRIO = {"label": 0, "list": 0, "rule": 1, "ner": 2}
INPUT_EXT = {".pdf", ".hwp", ".hwpx", ".png", ".tif", ".tiff", ".jpg", ".jpeg"}


def child_cpu() -> float:
    if resource is None:
        return 0.0
    ch = resource.getrusage(resource.RUSAGE_CHILDREN)
    return ch.ru_utime + ch.ru_stime


def rss_mb() -> float:
    if resource is None:
        return 0.0
    # macOS는 바이트, 리눅스는 KB 단위다
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rc = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    div = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(max(r, rc) / div, 1)


def footer_start(text: str) -> int | None:
    ms = list(re.finditer(r"(?m)^[^\n]{0,40}끝\.?\s*$", text))
    return ms[0].end() if ms else None


def official_context(text: str, s: int, e: int) -> bool:
    around = text[max(0, s - 8):s] + " " + text[e:e + 6]
    return bool(re.search(r"(주무관|팀장|과장|담당|기안자|검토자)", around))


def merge(spans: list[labels.Span]) -> list[labels.Span]:
    """겹치는 구간을 하나로 합친다. 종류·출처는 긴 쪽(같으면 우선순위 높은 쪽)을 따른다."""
    spans = sorted(spans, key=lambda s: (s.start, -(s.end - s.start), PRIO.get(s.source, 9)))
    out: list[labels.Span] = []
    for s in spans:
        if s.end <= s.start:
            continue
        if out and s.start < out[-1].end:
            cur = out[-1]
            if (s.end - s.start, -PRIO.get(s.source, 9)) > (cur.end - cur.start, -PRIO.get(cur.source, 9)):
                s2 = labels.Span(cur.start, max(cur.end, s.end), s.kind, s.source, s.key, s.review or cur.review,
                                 s.reason or cur.reason, s.role)
                out[-1] = s2
            else:
                cur.end = max(cur.end, s.end)
                cur.review = cur.review or s.review
            continue
        out.append(labels.Span(s.start, s.end, s.kind, s.source, s.key, s.review, s.reason, s.role))
    return out


def classify_org(text: str, sp: labels.Span, fs: int | None) -> str:
    if sp.kind == "PHONE" and rules.is_org_context(text, sp.start, fs):
        return "ORG_PHONE"
    if sp.kind == "ADDR":
        a, b = rules._line_bounds(text, sp.start)
        if re.search(r"우\s*\d{5}", text[a:b]):
            return "ORG_ADDR"
    return sp.kind


def process_text(text: str, profile: str, policy: dict, use_ner: bool, ner_stop: set[str], ocr: bool = False,
                 state: "learnstate.LearnState | None" = None):
    fix = profile == "fixed"
    st = state if state is not None else learnstate.load()
    orig_text = text
    # 오답 노트의 OCR 오독 글자 바로잡기(글자 수가 같아 위치가 그대로다). 찾기는 바로잡은 글로, 치환은 원문에 한다.
    text = learnstate.normalize(text, st.confusions)
    t = {}
    c0 = time.process_time()
    fs = footer_start(text)
    ld = labels.LabelDict(ROOT / "config/labels.yaml", text, extra=learnstate.extra_label_block(st))
    entries = labels.build_list(text, ld, fix, policy)
    spans = labels.apply_list(text, entries, fix)
    t["labels_cpu"] = time.process_time() - c0

    c0 = time.process_time()
    for h in rules.find_all(text, fix, fs, ocr):
        if h.kind.startswith("ORG") and not policy.get("mask_org_contact", True):
            continue
        spans.append(labels.Span(h.start, h.end, h.kind, "rule", h.rule, False, "", ""))
    # 직원이 승인한 추가 규칙(learn/rules_extra.yaml)
    extra_entries = []
    for s0, e0, kind, rid, add_list in learnstate.extra_rule_hits(text, st, ocr):
        if kind == "NAME":
            nm = text[s0:e0]
            if add_list:
                extra_entries.append(labels.Entry("NAME", nm, "", "rule", None, [(s0, e0)]))
            else:
                spans.append(labels.Span(s0, e0, "NAME", "rule", nm, False, rid, ""))
        else:
            spans.append(labels.Span(s0, e0, kind, "rule", rid, False, "", ""))
    if extra_entries:
        entries += extra_entries
        spans += labels.apply_list(text, extra_entries, fix)
    t["rules_cpu"] = time.process_time() - c0

    candidates = []
    c0 = time.process_time()
    if use_ner:
        import ner
        found = ner.find(text, ROOT / "models/ner/koelectra-ko-pii-ner", ner_stop, use_address=fix)
        known = {e.value for e in entries if e.kind == "NAME"}
        new_entries = []
        for f in found:
            covered = any(s.start <= f["start"] and f["end"] <= s.end for s in spans)
            if f["kind"] == "NAME":
                if covered or f["word"] in known or learnstate.is_exception(f["word"], st):
                    continue
                if fix:
                    # 고친 방식: 바로 뒤가 지명 접미사(가온군·나래구청)이거나 직함·결재 용어이면 이름이 아니다
                    nxt = text[f["end"]:f["end"] + 1]
                    if nxt and nxt in "군구시동읍면리로길청" or f["word"] in labels.TITLE_WORDS or f["word"] in labels.NOT_NAME:
                        continue
                    # '은하동장'·'가상구청장'처럼 지명 + 장(직함)
                    if f["word"][-1] in "동읍면리구군시" and nxt == "장":
                        continue
                    if labels.is_label_word(f["word"], ld):
                        continue
                    if re.search(rules.SIDO + r"\s*" + re.escape(f["word"]), text):   # '서울특별시 나래구' 같은 지명
                        continue
                if not f["masked"]:
                    candidates.append(f)
                    continue
                role = "담당공무원" if official_context(text, f["start"], f["end"]) else ""
                if role == "담당공무원" and not policy.get("mask_officials", True):
                    continue
                known.add(f["word"])
                new_entries.append(labels.Entry("NAME", f["word"], role, "ner", None, [(f["start"], f["end"])]))
            elif f["kind"] == "ADDR" and not covered:
                if f["masked"]:
                    spans.append(labels.Span(f["start"], f["end"], "ADDR", "ner", "NER_ADDRESS", True, "NER 주소", ""))
                else:
                    candidates.append(f)
        if new_entries:
            entries += new_entries
            spans += labels.apply_list(text, new_entries, fix)
    t["ner_cpu"] = time.process_time() - c0

    c0 = time.process_time()
    # 오답 노트의 예외 낱말: 라벨 칸 값이 아닌 곳에서 가린 같은 낱말은 풀어 둔다
    if st.exceptions:
        spans = [sp for sp in spans if sp.source == "label" or not learnstate.is_exception(text[sp.start:sp.end], st)]
    merged = merge(spans)
    for sp in merged:
        sp.kind = classify_org(text, sp, fs)
    merged = [sp for sp in merged if not (sp.kind.startswith("ORG") and not policy.get("mask_org_contact", True))]
    # 이름 번호 배정: 사망자 칸 이름을 먼저, 나머지는 처음 등장 순서
    name_no: dict[str, int] = {}
    dead = [e.value for e in entries if e.kind == "NAME" and e.role == "사망자"]
    for v in dead:
        name_no.setdefault(v, len(name_no) + 1)
    for sp in merged:
        if sp.kind == "NAME":
            name_no.setdefault(sp.key, len(name_no) + 1)
    roles = {}
    for e in entries:
        if e.kind == "NAME" and e.value in name_no and e.role:
            roles.setdefault(f"이름{name_no[e.value]}", e.role)
    out = orig_text
    recs = []
    for sp in sorted(merged, key=lambda s: s.start, reverse=True):
        repl = f"[이름{name_no[sp.key]}]" if sp.kind == "NAME" else KIND_TAG[sp.kind]
        recs.append({"start": sp.start, "end": sp.end, "kind": sp.kind, "source": sp.source, "key": sp.key,
                     "orig": orig_text[sp.start:sp.end], "repl": repl, "review": sp.review, "reason": sp.reason,
                     "role": sp.role})
        out = out[:sp.start] + repl + out[sp.end:]
    recs.reverse()
    t["replace_cpu"] = time.process_time() - c0

    # 누출 재검사
    c0 = time.process_time()
    leaks = 0
    out_n = learnstate.normalize(out, st.confusions)
    for e in entries:
        if e.kind == "NAME":
            pat = labels.name_variants(e.value, e.hanja, fix)[0][0]
            leaks += len(re.findall(pat, out_n))
        elif e.kind in ("RRN", "PHONE"):
            p = labels.number_pattern(e.value)
            if p:
                leaks += len(re.findall(p, out_n))
    for h in rules.find_all(out_n, fix, footer_start(out_n), ocr):
        if h.kind in ("RRN", "PHONE"):
            leaks += 1
        elif h.kind == "ORG_PHONE" and policy.get("mask_org_contact", True):
            leaks += 1
    t["recheck_cpu"] = time.process_time() - c0
    return out, recs, candidates, roles, leaks, t, entries


def front_matter(doc_id, st, roles, review, ocr_mean):
    rl = ", ".join(f"{k}: {v}" for k, v in sorted(roles.items(), key=lambda x: int(x[0][2:])))
    return (f"---\ndoc_id: {doc_id}\nmasked: true\nsource_type: {st}\nroles: {{{rl}}}\n"
            f"review: {review}\nocr_mean_confidence: {ocr_mean if ocr_mean is not None else 'null'}\n---\n\n")


def next_doc_id(maps_dir: Path) -> str:
    day = dt.date.today().strftime("%Y%m%d")
    n = len(list(maps_dir.glob(f"{day}-*.map.json"))) + 1
    return f"{day}-{n:03d}"


def cmd_run(a):
    import extract
    import review
    import ner as _ner  # noqa: F401  (시간 측정에서 import 비용을 첫 문서에 몰지 않으려고 먼저 읽는다)

    out_root = Path(a.out).resolve() if a.out else ROOT
    test_mode = a.out is not None
    dirs = {k: out_root / v for k, v in {"pending": "pending", "maps": "secure/maps", "review": "secure/review",
                                         "work": "secure/work", "orig": "secure/originals", "logs": "logs"}.items()}
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    netguard.install(str(dirs["logs"] / "netguard.log"))
    policy = yaml.safe_load((ROOT / "config/policy.yaml").read_text(encoding="utf-8"))
    import ner
    ner_stop = ner.load_stopwords(ROOT / "config/ner_stopwords.txt")
    Path(a.inbox).mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in Path(a.inbox).iterdir() if p.suffix.lower() in INPUT_EXT)
    print(f"처리할 공문 {len(files)}건")
    if a.only:
        keys = a.only.split(",")
        files = [p for p in files if any(k in p.name for k in keys)]
    use_ner = not a.no_ner
    rotate_below = float(policy.get("fax_rotate_below", 0.8))
    for p in files:
        doc_id = next_doc_id(dirs["maps"])
        w0, c0 = time.time(), time.process_time()
        ch0 = child_cpu()
        try:
            st, text, info = extract.extract(p, dirs["work"], doc_id, dirs["logs"] / "netguard.log",
                                             fax_method=a.fax_method, det=a.det, prep=a.prep,
                                             scan_engine=a.scan_engine, rotate_below=rotate_below)
        except Exception as ex:  # noqa: BLE001
            print(f"{doc_id} 읽기 실패: {type(ex).__name__}")
            continue
        ext_cpu = time.process_time() - c0 + (child_cpu() - ch0)
        ext_wall = time.time() - w0
        masked, recs, cands, roles, leaks, t, entries = process_text(text, a.profile, policy, use_ner, ner_stop,
                                                                     ocr=st in ("pdf-ocr", "fax"))
        need_review = any(r["review"] for r in recs) or bool(cands) or (info.get("mean_conf", 1) < rotate_below)
        status = "failed" if leaks else "pending"
        (dirs["pending"] / f"{doc_id}.md").write_text(
            front_matter(doc_id, st, roles, status, info.get("mean_conf")) + masked, encoding="utf-8")
        mp = {"doc_id": doc_id, "original_filename": p.name,
              "created": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
              "profile": a.profile, "ner": use_ner, "source_type": st, "ocr": info,
              "map": {}, "spans": recs, "ner_candidates": cands, "recheck_leaks": leaks}
        for r in recs:
            if r["kind"] == "NAME":
                mp["map"][r["repl"]] = r["key"]
            else:
                mp["map"].setdefault(r["repl"], [])
                if r["orig"] not in mp["map"][r["repl"]]:
                    mp["map"][r["repl"]].append(r["orig"])
        (dirs["maps"] / f"{doc_id}.map.json").write_text(json.dumps(mp, ensure_ascii=False, indent=1), encoding="utf-8")
        review.write(dirs["review"], doc_id, text, masked, recs, cands)
        if test_mode:
            shutil.copy2(p, dirs["orig"] / f"{doc_id}{p.suffix.lower()}")   # 시험 모드: 원본은 복사만 한다
        else:
            shutil.move(str(p), dirs["orig"] / f"{doc_id}{p.suffix.lower()}")
        metric = {"doc_id": doc_id, "source_type": st, "profile": a.profile, "ner": use_ner,
                  "fax_method": a.fax_method if st in ("fax",) else None,
                  "extract_cpu_s": round(ext_cpu, 2), "extract_wall_s": round(ext_wall, 2),
                  **{k: round(v, 3) for k, v in t.items()},
                  "total_cpu_s": round(ext_cpu + sum(t.values()), 2),
                  "total_wall_s": round(time.time() - w0, 2),
                  "max_rss_mb": rss_mb(), "spans": len(recs), "review_flags": sum(r["review"] for r in recs),
                  "ner_candidates": len(cands), "recheck_leaks": leaks, "status": status,
                  "ocr_mean_conf": info.get("mean_conf"), "rotated": info.get("rotated")}
        with open(dirs["logs"] / "metrics.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(metric, ensure_ascii=False) + "\n")
        print(f"{doc_id} {st} 가림 {len(recs)}건 검수표시 {metric['review_flags']}건 상태 {status} "
              f"CPU {metric['total_cpu_s']}s")


def cmd_approve(a):
    import approve
    out_root = Path(a.out).resolve() if a.out else ROOT
    print(approve.approve_doc(out_root, a.doc_id))


def cmd_review(a):
    import review_server
    review_server.serve(Path(a.out).resolve() if a.out else ROOT, a.port)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--inbox", default=str(ROOT / "inbox"))
    r.add_argument("--out", default=None)
    r.add_argument("--profile", choices=["spec", "fixed"], default="fixed")
    r.add_argument("--no-ner", action="store_true")
    r.add_argument("--fax-method", choices=["A", "B"], default="A")
    r.add_argument("--det", choices=["mobile", "server"], default="mobile")
    r.add_argument("--prep", choices=["gray8", "none"], default="gray8")
    r.add_argument("--scan-engine", choices=["kordoc", "paddle"], default="kordoc")
    r.add_argument("--only", default=None, help="파일 이름에 들어간 낱말로 거르기(쉼표 구분)")
    r.set_defaults(func=cmd_run)
    p = sub.add_parser("approve")
    p.add_argument("doc_id")
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_approve)
    v = sub.add_parser("review", help="검수 화면(오답 노트 표시)을 이 PC 안에서만 연다")
    v.add_argument("--out", default=None)
    v.add_argument("--port", type=int, default=8765)
    v.set_defaults(func=cmd_review)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
