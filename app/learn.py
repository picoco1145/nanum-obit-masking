"""오답 노트: 검수 표시를 모아 목록을 고치고, 고칠 수 없는 것은 가짜화한 수정 요청으로 넘긴다.

폴더
- <out>/secure/learn/          진짜 값이 들어가는 곳(PC 밖으로 내보내지 않는다)
    marks/<문서번호>.json      검수 화면에서 남긴 표시(놓침·잘못 가림)
    notebook.jsonl             반영한 표시의 기록(진짜 값 포함)
    ingested.json              이미 반영한 표시 파일의 지문
    pending_words.json         이름처럼 보여 직원 승인을 기다리는 예외 낱말
- learn/ (NANUM_LEARN_DIR)     진짜 값이 없는 곳
    learned.yaml               자동 반영한 낱말(라벨·예외·오독 글자)
    rules_extra.yaml           직원이 승인한 정규식
    held.jsonl                 회귀 시험에 걸려 보류한 것
    proposals/requests/*.json  가짜화한 수정 요청(Claude Code가 이것만 보고 수정안을 쓴다)
    proposals/drafts/*.yaml    수정안
    proposals/status.json      수정안 검사·승인 상태
    regress/cases/*.json       가짜화한 지난 오답(회귀 세트)
    reports/                   주간 보고(발송하지 않는다)
    history.jsonl              사건 기록(진짜 값 없음)

명령
  learn.py ingest --out OUT         표시를 반영한다(자동 반영 → 회귀 시험 → 요청 만들기)
  learn.py check DRAFT_ID           수정안을 회귀 시험에 돌린다
  learn.py approve DRAFT_ID         검사를 통과한 수정안을 적용한다(직원 승인)
  learn.py reject DRAFT_ID
  learn.py words --out OUT          승인 대기 낱말 목록
  learn.py approve-word N --out OUT / reject-word N --out OUT
  learn.py report [--days 7]        주간 보고 파일을 만든다
  learn.py status                   현재 상태 요약
  learn.py init-base --from RUN --fake FAKE   기존 시험 세트로 회귀 기준을 만든다
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

APP = Path(__file__).resolve().parent
ROOT = APP.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(ROOT / "tests"))

import fakeify  # noqa: E402
import labels  # noqa: E402
import learnstate  # noqa: E402
import mask  # noqa: E402

BASE_DIR = ROOT / "tests/regress/base"
_POLICY = None
_STOP = None
_CACHE: dict = {}


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def policy():
    global _POLICY, _STOP
    if _POLICY is None:
        import ner
        _POLICY = yaml.safe_load((ROOT / "config/policy.yaml").read_text(encoding="utf-8"))
        _STOP = ner.load_stopwords(ROOT / "config/ner_stopwords.txt")
    return _POLICY, _STOP


def run_text(text: str, st: learnstate.LearnState, ocr: bool, profile: str = "fixed", use_ner: bool = True):
    pol, stop = policy()
    out, recs, cands, roles, leaks, t, entries = mask.process_text(text, profile, pol, use_ner, stop, ocr=ocr, state=st)
    return out, recs, cands, entries


def covered_text(text, recs, s, e) -> bool:
    """[s, e) 안의 글자(공백 제외)가 모두 가린 구간 안에 있으면 참."""
    return all(text[i].isspace() or any(r["start"] <= i < r["end"] for r in recs) for i in range(s, e))


def touched(recs, s, e) -> bool:
    return any(r["start"] < e and s < r["end"] for r in recs)


def history(ld: Path, event: str, **kw):
    ld.mkdir(parents=True, exist_ok=True)
    with open(ld / "history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": now(), "event": event, **kw}, ensure_ascii=False) + "\n")


def rjson(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def wjson(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 회귀 시험
def base_docs():
    meta = rjson(BASE_DIR / "meta.json", [])
    return meta


def run_base(st: learnstate.LearnState) -> dict:
    """기존 시험 세트(26건)를 엄격 채점한다. {파일: (놓침, 금지값 가림)}"""
    key = ("base", st.key())
    if key in _CACHE:
        return _CACHE[key]
    import evaluate
    evaluate.STRICT = True
    res = {}
    for m in base_docs():
        text = (BASE_DIR / "texts" / f"{m['file']}.md").read_text(encoding="utf-8")
        ans = json.loads((BASE_DIR / "answers" / f"{m['doc']}.answer.json").read_text(encoding="utf-8"))
        src = (BASE_DIR / "src" / f"{m['doc']}.md").read_text(encoding="utf-8")
        out, recs, _, _ = run_text(text, st, m["source_type"] in ("pdf-ocr", "fax"), m.get("profile", "fixed"),
                                   m.get("ner", True))
        r = evaluate.eval_doc({"spans": recs}, text, out, ans, m["fmt"], src)
        res[m["file"]] = (len(r["leaks"]), len(r["over"]))
    _CACHE[key] = res
    return res


def case_files(ld: Path):
    return sorted((ld / "regress/cases").glob("*.json"))


def run_cases(st: learnstate.LearnState, ld: Path) -> dict:
    """회귀 세트(가짜화한 지난 오답). {사례: (놓침, 금지값 가림)}"""
    res = {}
    for cf in case_files(ld):
        c = json.loads(cf.read_text(encoding="utf-8"))
        key = ("case", c["id"], st.key())
        if key not in _CACHE:
            out, recs, _, _ = run_text(c["text"], st, c.get("ocr", False))
            miss = sum(1 for s, e, k in c["must_mask"] if not covered_text(c["text"], recs, s, e))
            over = sum(1 for s, e in c["must_not"] if touched(recs, s, e))
            _CACHE[key] = (miss, over)
        res[c["id"]] = _CACHE[key]
    return res


def pytest_ok() -> bool:
    key = ("pytest",)
    if key not in _CACHE:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests/test_rules.py")],
                           capture_output=True, text=True, cwd=str(ROOT))
        _CACHE[key] = r.returncode == 0
    return _CACHE[key]


def gate(cand: learnstate.LearnState, cur: learnstate.LearnState, ld: Path) -> tuple[bool, dict]:
    """하나라도 나빠지면 거부한다: 기존 세트 놓침·금지값 가림, 회귀 세트 놓침·금지값 가림, 규칙 단위 시험."""
    b0, b1 = run_base(cur), run_base(cand)
    c0, c1 = run_cases(cur, ld), run_cases(cand, ld)
    worse = []
    for k in b0:
        if b1[k][0] > b0[k][0]:
            worse.append(f"기존 세트 {k} 놓침 {b0[k][0]}→{b1[k][0]}")
        if b1[k][1] > b0[k][1]:
            worse.append(f"기존 세트 {k} 금지값 가림 {b0[k][1]}→{b1[k][1]}")
    for k in c0:
        if c1[k][0] > c0[k][0]:
            worse.append(f"회귀 사례 {k} 놓침 {c0[k][0]}→{c1[k][0]}")
        if c1[k][1] > c0[k][1]:
            worse.append(f"회귀 사례 {k} 금지값 가림 {c0[k][1]}→{c1[k][1]}")
    pt = pytest_ok()
    if not pt:
        worse.append("규칙 단위 시험(pytest) 실패")
    rep = {"base_miss": [sum(v[0] for v in b0.values()), sum(v[0] for v in b1.values())],
           "base_over": [sum(v[1] for v in b0.values()), sum(v[1] for v in b1.values())],
           "cases_miss": [sum(v[0] for v in c0.values()), sum(v[0] for v in c1.values())],
           "cases_over": [sum(v[1] for v in c0.values()), sum(v[1] for v in c1.values())],
           "cases": len(c0), "pytest": pt, "worse": worse}
    return not worse, rep


# ---------------------------------------------------------------- 표시 분류
ROLE_HINT = [("사망자", ("사망", "고인", "망인", "변사", "환자", "입원", "입소", "대상", "본인", "망")),
             ("신고인", ("신고", "발견", "의뢰", "신청")),
             ("담당공무원", ("담당", "주무관", "기안", "작성자")),
             ("연고자", ("보호", "연고", "가족", "유족", "상주", "친족", "인수", "자녀", "배우자"))]


def guess_role(word: str) -> str:
    for role, keys in ROLE_HINT:
        if any(k in word for k in keys):
            return role
    return "연고자"


def name_like(w: str) -> bool:
    """이름처럼 보이는 낱말: 성씨 글자로 시작하는 2~3음절, 또는 두 글자 성씨로 시작하는 4음절."""
    w = re.sub(r"\s+", "", w)
    if not re.fullmatch(r"[가-힣]{2,4}", w):
        return False
    if w[:2] in labels.TWO_CHAR_SURNAMES:
        return True
    return len(w) <= 3 and w[0] in labels.SURNAMES


def cell_at(text: str, s: int, e: int):
    for tb in labels.parse_tables(text):
        for c in tb:
            if c.start <= s and e <= c.end:
                return c, tb
    return None, None


def neighbor(tb, c, d: int):
    """같은 줄에서 d=+1이면 오른쪽, -1이면 왼쪽 칸."""
    row = sorted((x for x in tb if x.row == c.row), key=lambda x: x.col)
    i = row.index(c)
    j = i + d
    return row[j] if 0 <= j < len(row) else None


def label_before(text: str, s: int):
    """'낱말:' 꼴로 값 앞에 붙은 칸 이름(같은 줄)."""
    ls = text.rfind("\n", 0, s) + 1
    m = re.search(r"([가-힣A-Za-z()·]{2,12})\s*[:：]\s*$", text[ls:s])
    if m:
        return m.group(1), ls + m.start(1), ls + m.end(1)
    return None


def add_label(st: learnstate.LearnState, kind: str, role: str, word: str):
    st = st.copy()
    word = labels.norm_label(word) or word
    if kind == "NAME":
        blk = st.labels.setdefault("NAME", {})
        lst = blk.setdefault(role or "연고자", [])
    else:
        lst = st.labels.setdefault(kind, [])
    if word not in lst:
        lst.append(word)
    return st


def add_exception(st, word):
    st = st.copy()
    w = re.sub(r"\s+", "", word)
    if w not in st.exceptions:
        st.exceptions.append(w)
    return st


def add_confusions(st, conf: dict):
    st = st.copy()
    st.confusions.update(conf)
    return st


def label_candidate_for_value(text, s, e, kind, ld_now):
    """값 [s,e) 앞의 칸 이름이 아직 라벨이 아니면 (낱말) 후보."""
    c, tb = cell_at(text, s, e)
    if c is not None:
        left = neighbor(tb, c, -1)
        if left is not None:
            w = left.text.strip().lstrip("…·.").strip()
            if w and len(w) <= 12 and re.search(r"[가-힣A-Za-z]", w) and ld_now.lookup(w) is None:
                return w
        return None
    lb = label_before(text, s)
    if lb and ld_now.lookup(lb[0]) is None:
        return lb[0]
    return None


def confusion_candidates(seg: str, known: dict) -> dict:
    conf = {}
    for c in seg:
        if c.isspace() or c in "-–—.*\\()" or c.isdigit() or c in fakeify.KDIGIT or c in known:
            continue
        if c in fakeify.LATIN_CONF:
            conf[c] = fakeify.LATIN_CONF[c]
        elif fakeify.is_hangul(c):
            k, dist = fakeify.closest_kdigit(c)
            if dist <= 1.0:
                conf[c] = fakeify.KDIGIT[k]
    return conf


# ---------------------------------------------------------------- 반영
def learned_words(st) -> set:
    out = set(st.exceptions)
    for v in st.labels.values():
        for x in (v.values() if isinstance(v, dict) else [v]):
            out |= {labels.norm_label(w) for w in x}
    return out


PLACE_RX = re.compile(r"([가-힣]{2})(시|군|구|읍|면)(?=청|수|장|의회|보건|민|[^가-힣]|$)|"
                      r"([가-힣]{2})(?=대학교|대학병원|병원|경찰서|소방서|보건소|요양원|의료원)")


def extend_spans(text: str, spans: list) -> list:
    """가릴 값의 다른 등장(이름 전체, 주소의 지명 핵심어)도 가짜화 구간에 넣는다.
    예: 주소 '가람구'를 바꾸면 기관 이름 '가람경찰서'의 '가람'도 같이 바꿔야 원래 지명이 남지 않는다.
    기관 이름에 들어간 지명(가온군수·가온대학교병원)도 사망자 주소의 지명과 같을 수 있으므로 함께 바꾼다."""
    out = list(spans)
    keep = fakeify.keep_words()

    def free(a, b):
        return not any(x < b and a < y for x, y, _ in out)

    words = []
    for m in PLACE_RX.finditer(text):
        core = m.group(1) or m.group(3)
        if not fakeify.SIDO_RX.match(core + (m.group(2) or "")) and core not in keep:
            words.append((core, "ADDR"))
    for s, e, k in spans:
        v = text[s:e]
        if k in ("ADDR", "ORG_ADDR"):
            for tok in re.findall(r"[가-힣]{2,}", v):
                suf = next((x for x in fakeify.ADDR_SUFFIX if tok.endswith(x) and len(tok) > len(x)), "")
                core = tok[:len(tok) - len(suf)] if suf else tok
                if not fakeify.SIDO_RX.match(tok) and len(core) >= 2:
                    words.append((core, "ADDR"))
        elif k == "NAME":
            nm = re.sub(r"\s+", "", v)
            if re.fullmatch(r"[가-힣]{2,5}", nm):
                words.append((nm, "NAME"))
    for w, kk in dict.fromkeys(words):
        for m in re.finditer(re.escape(w), text):
            if free(m.start(), m.end()):
                out.append((m.start(), m.end(), kk))
    return out


def apply(stx, c):
    if c["type"] == "label":
        return add_label(stx, c["kind"], c["role"], c["word"])
    if c["type"] == "exception":
        return add_exception(stx, c["word"])
    return add_confusions(stx, c["map"])


def load_doc(out: Path, doc_id: str):
    text = (out / "secure/work" / f"{doc_id}.md").read_text(encoding="utf-8")
    mp = json.loads((out / "secure/maps" / f"{doc_id}.map.json").read_text(encoding="utf-8"))
    return text, mp


def mark_files(out: Path):
    return sorted((out / "secure/learn/marks").glob("*.json"))


def fhash(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


def ingest(out: Path, ld: Path | None = None, log=print) -> dict:
    ld = ld or learnstate.learn_dir()
    sec = out / "secure/learn"
    ing = rjson(sec / "ingested.json", {})
    todo = [p for p in mark_files(out) if ing.get(p.name) != fhash(p)]
    summary = {"docs": 0, "miss": 0, "over": 0, "auto": [], "held": [], "pending_words": 0, "requests": [],
               "cases": [], "fake_fail": 0}
    if not todo:
        log("새로 반영할 표시가 없습니다.")
        return summary
    st = learnstate.load(ld)
    docs = []
    for p in todo:
        mk = json.loads(p.read_text(encoding="utf-8"))
        did = mk["doc_id"]
        text, mp = load_doc(out, did)
        ocr = mp["source_type"] in ("pdf-ocr", "fax")
        docs.append((p, did, text, mp, ocr, mk["marks"]))
        with open(sec / "notebook.jsonl", "a", encoding="utf-8") as f:
            for m in mk["marks"]:
                f.write(json.dumps({"ts": now(), "doc_id": did, **m}, ensure_ascii=False) + "\n")
        nm = sum(m["type"] == "miss" for m in mk["marks"])
        no = sum(m["type"] == "over" for m in mk["marks"])
        summary["docs"] += 1
        summary["miss"] += nm
        summary["over"] += no
        history(ld, "marks", doc_id=did, miss=nm, over=no,
                miss_kinds=sorted({m["kind"] for m in mk["marks"] if m["type"] == "miss"}))

    # 1) 후보 만들기: 표시 하나마다 고칠 낱말을 찾고, 그 문서에서 실제로 고쳐지는지 확인한다
    cands = []      # (설명, 적용 함수, [(문서, 확인 함수)])
    leftovers = []  # 자동으로 못 고친 놓침
    pend = rjson(sec / "pending_words.json", [])
    for p, did, text, mp, ocr, marks in docs:
        ld_now = labels.LabelDict(ROOT / "config/labels.yaml", text, extra=learnstate.extra_label_block(st))
        _, recs0, _, _ = run_text(text, st, ocr)

        def first(m):
            c, _ = cell_at(text, m["start"], m["end"])
            return (m["type"] != "over", not (c is not None and c.text.strip() == text[m["start"]:m["end"]].strip()))

        for m in sorted(marks, key=first):
            s, e = m["start"], m["end"]
            # 앞의 표시로 만든 후보가 이미 이 표시를 고쳤으면 넘어간다
            if cands:
                st_try = st
                for c in cands:
                    st_try = apply(st_try, c)
                _, rt, _, _ = run_text(text, st_try, ocr)
                if (m["type"] == "over" and not touched(rt, s, e)) or \
                        (m["type"] == "miss" and covered_text(text, rt, s, e)):
                    continue
            if m["type"] == "over":
                word = text[s:e].strip()
                tried = []
                c, tb = cell_at(text, s, e)
                if c is not None and c.text.strip() == word:
                    right = neighbor(tb, c, +1)
                    if right is not None and touched(recs0, right.start, right.end):
                        kind = next(r["kind"] for r in recs0 if r["start"] < right.end and right.start < r["end"])
                        tried.append(("label", kind, guess_role(word) if kind == "NAME" else "", word, right.start, right.end))
                else:
                    after = text[e:e + 3]
                    if re.match(r"\s*[:：]", after):
                        vm = re.match(r"\s*[:：]\s*([^\n,]{1,20})", text[e:])
                        if vm:
                            vs, ve = e + vm.start(1), e + vm.end(1)
                            if touched(recs0, vs, ve):
                                kind = next(r["kind"] for r in recs0 if r["start"] < ve and vs < r["end"])
                                tried.append(("label", kind, guess_role(word) if kind == "NAME" else "", word, vs, ve))
                ok = False
                for t in tried:
                    _, kind, role, w, vs, ve = t
                    st2 = add_label(st, kind, role, w)
                    _, recs1, _, _ = run_text(text, st2, ocr)
                    if not touched(recs1, s, e) and touched(recs1, vs, ve):
                        cands.append({"type": "label", "kind": kind, "role": role, "word": labels.norm_label(w) or w,
                                      "doc": did})
                        ok = True
                        break
                if ok:
                    continue
                if name_like(word):
                    if not any(x["word"] == word and x["status"] == "대기" for x in pend):
                        pend.append({"n": len(pend) + 1, "word": word, "doc_id": did, "start": s, "end": e,
                                     "created": now(), "status": "대기"})
                    summary["pending_words"] += 1
                    continue
                st2 = add_exception(st, word)
                _, recs1, _, _ = run_text(text, st2, ocr)
                if not touched(recs1, s, e):
                    cands.append({"type": "exception", "word": re.sub(r"\s+", "", word), "doc": did})
                else:
                    leftovers.append((did, m, "예외 낱말로 풀리지 않음"))
            else:
                kind = m["kind"]
                fixed = False
                if kind in ("RRN", "PHONE"):
                    conf = confusion_candidates(text[s:e], st.confusions)
                    if conf:
                        st2 = add_confusions(st, conf)
                        _, recs1, _, _ = run_text(text, st2, ocr)
                        if covered_text(text, recs1, s, e):
                            cands.append({"type": "confusion", "map": conf, "doc": did})
                            fixed = True
                if not fixed:
                    w = label_candidate_for_value(text, s, e, kind, ld_now)
                    if w:
                        st2 = add_label(st, kind, guess_role(w) if kind == "NAME" else "", w)
                        _, recs1, _, _ = run_text(text, st2, ocr)
                        if covered_text(text, recs1, s, e):
                            cands.append({"type": "label", "kind": kind, "role": guess_role(w) if kind == "NAME" else "",
                                          "word": labels.norm_label(w) or w, "doc": did})
                            fixed = True
                if not fixed:
                    leftovers.append((did, m, "낱말 추가로 고쳐지지 않음"))
    wjson(sec / "pending_words.json", pend)

    # 2) 자동 반영: 후보를 모두 넣고 회귀 시험. 걸리면 하나씩 넣어 보며 통과한 것만 남긴다
    def desc(c):
        if c["type"] == "label":
            return f"라벨 추가: {c['word']} → {c['kind']}{'/' + c['role'] if c['role'] else ''}"
        if c["type"] == "exception":
            return f"예외 낱말 추가: {c['word']}"
        return "오독 글자 추가: " + ", ".join(f"{k}→{v}" for k, v in c["map"].items())

    # 같은 후보는 하나로
    uniq, seen = [], set()
    for c in cands:
        k = desc(c)
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    accepted = st
    if uniq:
        all_st = st
        for c in uniq:
            all_st = apply(all_st, c)
        ok, rep = gate(all_st, st, ld)
        if ok:
            accepted = all_st
            for c in uniq:
                summary["auto"].append(desc(c))
            history(ld, "auto_apply", items=[desc(c) for c in uniq], gate=rep)
        else:
            for c in uniq:
                trial = apply(accepted, c)
                ok1, rep1 = gate(trial, accepted, ld)
                if ok1:
                    accepted = trial
                    summary["auto"].append(desc(c))
                    history(ld, "auto_apply", items=[desc(c)], gate=rep1)
                else:
                    summary["held"].append({"item": desc(c), "why": rep1["worse"]})
                    with open(ld / "held.jsonl", "a", encoding="utf-8") as f:
                        f.write(json.dumps({"ts": now(), "item": desc(c), "why": rep1["worse"]}, ensure_ascii=False) + "\n")
                    history(ld, "hold", item=desc(c), why=rep1["worse"])
        if accepted is not st:
            learnstate.save_learned(accepted, ld)
    st = accepted

    # 3) 가짜화한 회귀 사례와 수정 요청
    fakeify.EXTRA_KEEP = learned_words(st)
    for p, did, text, mp, ocr, marks in docs:
        _, recs_now, cands_now, entries = run_text(text, st, ocr)
        over_sp = [(m["start"], m["end"]) for m in marks if m["type"] == "over"]
        sens = [(r["start"], r["end"], r["kind"]) for r in mp["spans"]
                if not any(a < r["end"] and r["start"] < b for a, b in over_sp)]
        sens += [(m["start"], m["end"], m["kind"]) for m in marks if m["type"] == "miss"]
        fake_spans = sens + [(c["start"], c["end"], "NAME") for c in (mp.get("ner_candidates") or []) + cands_now
                             if c["kind"] == "NAME" and not any(a < c["end"] and c["start"] < b for a, b in over_sp)]
        values = [(k, text[s:e]) for s, e, k in sens] + [(e_.kind, e_.value) for e_ in entries
                                                          if e_.kind in ("NAME", "RRN", "PHONE")]
        fake_spans = extend_spans(text, fake_spans)
        fake, done, probs = fakeify.fakeify_checked(text, fake_spans, values, st.confusions)
        if fake is None:
            summary["fake_fail"] += 1
            history(ld, "fake_fail", doc_id=did, problems=probs)
            for did2, m, why in leftovers:
                if did2 == did:
                    summary["held"].append({"item": f"{did} 놓침({m['kind']}) 수정 요청", "why": ["가짜화 검사 실패"]})
            continue
        cid = "c-" + hashlib.sha1((did + fake).encode()).hexdigest()[:8]
        case = {"id": cid, "created": now(), "doc_id": did, "ocr": ocr, "origin": "오답 노트",
                "fake_check": "통과(원래 값이 남지 않음)", "text": fake,
                "must_mask": [[s, e, k] for s, e, k in sens],
                "must_not": [[s, e] for s, e in over_sp]}
        wjson(ld / "regress/cases" / f"{cid}.json", case)
        summary["cases"].append(cid)
        _, frecs, _, _ = run_text(fake, st, ocr)
        for did2, m, why in leftovers:
            if did2 != did or m["type"] != "miss":
                continue
            s, e = m["start"], m["end"]
            if covered_text(text, recs_now, s, e):
                continue          # 다른 반영으로 이미 고쳐졌다
            reproduced = not covered_text(fake, frecs, s, e)
            ws = text.rfind("\n", 0, max(0, text.rfind("\n", 0, s))) + 1
            we = text.find("\n", text.find("\n", e) + 1)
            we = len(text) if we < 0 else we
            ws, we = max(ws, s - 300), min(we, e + 300)
            win = fake[ws:we]
            shape = " ".join(fakeify.glyph_class(c) if not c.isspace() else "_" for c in fake[s:e])
            qid = "q-" + hashlib.sha1((cid + str(s)).encode()).hexdigest()[:8]
            req = {"id": qid, "case_id": cid, "created": now(), "kind": m["kind"], "ocr": ocr,
                   "window": win, "target": [s - ws, e - ws], "target_text": fake[s:e],
                   "masked_in_window": [[r["start"] - ws, r["end"] - ws, r["kind"]] for r in frecs
                                        if r["start"] >= ws and r["end"] <= we],
                   "reproduced": reproduced, "shape": shape,
                   "note": "가짜화한 문서에서 같은 자리를 " + ("여전히 놓친다" if reproduced else "가린다(재현 안 됨)")}
            wjson(ld / "proposals/requests" / f"{qid}.json", req)
            summary["requests"].append(qid)
            history(ld, "request", id=qid, case=cid, kind=m["kind"], reproduced=reproduced)
        history(ld, "case", id=cid, doc_id=did, must_mask=len(sens), must_not=len(over_sp))
    for p in todo:
        ing[p.name] = fhash(p)
    wjson(sec / "ingested.json", ing)
    history(ld, "ingest", docs=summary["docs"], miss=summary["miss"], over=summary["over"],
            auto=len(summary["auto"]), held=len(summary["held"]), requests=len(summary["requests"]),
            pending_words=summary["pending_words"])
    log(json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


# ---------------------------------------------------------------- 승인 대기 낱말
def words(out: Path):
    return rjson(out / "secure/learn/pending_words.json", [])


def decide_word(out: Path, n: int, approve: bool, ld: Path | None = None, log=print) -> str:
    ld = ld or learnstate.learn_dir()
    path = out / "secure/learn/pending_words.json"
    pend = rjson(path, [])
    it = next((x for x in pend if x["n"] == n), None)
    if it is None or it["status"] != "대기":
        return "대기 중인 낱말이 아닙니다."
    if not approve:
        it["status"] = "거절"
        wjson(path, pend)
        history(ld, "word_reject", n=n)
        return "거절했습니다."
    st = learnstate.load(ld)
    st2 = add_exception(st, it["word"])
    ok, rep = gate(st2, st, ld)
    if not ok:
        it["status"] = "보류(회귀 시험)"
        wjson(path, pend)
        history(ld, "hold", item=f"승인 낱말 {n}번", why=rep["worse"])
        return "회귀 시험에서 나빠지는 곳이 있어 보류했습니다: " + "; ".join(rep["worse"])
    learnstate.save_learned(st2, ld)
    it["status"] = "승인"
    wjson(path, pend)
    history(ld, "word_approve", n=n, item=f"예외 낱말 추가: {it['word']}")
    return "예외 낱말로 추가했습니다."


# ---------------------------------------------------------------- 수정안
def drafts(ld: Path):
    return sorted((ld / "proposals/drafts").glob("*.yaml"))


def load_status(ld):
    return rjson(ld / "proposals/status.json", {})


def check_draft(did: str, ld: Path | None = None) -> dict:
    ld = ld or learnstate.learn_dir()
    d = yaml.safe_load((ld / "proposals/drafts" / f"{did}.yaml").read_text(encoding="utf-8"))
    st = learnstate.load(ld)
    reasons = []
    try:
        rx = re.compile(d["pattern"], re.M)
    except re.error as ex:
        reasons.append(f"정규식 오류: {ex}")
        rx = None
    if d.get("kind") not in ("NAME", "RRN", "PHONE", "ADDR"):
        reasons.append("kind는 NAME/RRN/PHONE/ADDR 가운데 하나여야 합니다")
    fixed_req = []
    if rx is not None:
        for t in (d.get("tests") or {}).get("hit") or []:
            if not rx.search(t):
                reasons.append("hit 예문에 맞지 않음")
        for t in (d.get("tests") or {}).get("miss") or []:
            if rx.search(t):
                reasons.append("miss 예문에 맞아 버림")
        rule = {"id": did, "kind": d.get("kind"), "pattern": d["pattern"], "scope": d.get("scope", "all"),
                "add_to_list": bool(d.get("add_to_list"))}
        for qid in d.get("request_ids") or []:
            q = rjson(ld / "proposals/requests" / f"{qid}.json", None)
            if q is None:
                reasons.append(f"요청 {qid} 없음")
                continue
            tmp = learnstate.LearnState(rules=[rule])
            hits = learnstate.extra_rule_hits(q["window"], tmp, True)
            a, b = q["target"]
            if all(any(s <= i < e for s, e, *_ in hits) for i in range(a, b) if not q["window"][i].isspace()):
                fixed_req.append(qid)
            else:
                reasons.append(f"요청 {qid}의 놓친 자리를 덮지 못함")
        st2 = st.copy()
        st2.rules = st2.rules + [rule]
        ok, rep = gate(st2, st, ld)
        if not ok:
            reasons += rep["worse"]
    else:
        rep = {}
    res = {"state": "검사 통과" if not reasons else "검사 실패", "reasons": reasons, "gate": rep,
           "fixed_requests": fixed_req, "learn_key": st.key(), "checked": now()}
    stt = load_status(ld)
    old = stt.get(did, {})
    if old.get("state") in ("승인", "거절"):
        res["state"] = old["state"]
    stt[did] = res
    wjson(ld / "proposals/status.json", stt)
    history(ld, "check", id=did, state=res["state"], reasons=reasons, gate=rep)
    return res


def approve_draft(did: str, ld: Path | None = None, who: str = "직원") -> str:
    ld = ld or learnstate.learn_dir()
    stt = load_status(ld)
    st = learnstate.load(ld)
    cur = stt.get(did)
    if cur and cur.get("state") == "승인":
        return "이미 승인한 수정안입니다."
    if not cur or cur.get("learn_key") != st.key() or cur.get("state") != "검사 통과":
        cur = check_draft(did, ld)
    if cur["state"] != "검사 통과":
        return "회귀 시험을 통과하지 못해 적용하지 않았습니다: " + "; ".join(cur["reasons"])
    d = yaml.safe_load((ld / "proposals/drafts" / f"{did}.yaml").read_text(encoding="utf-8"))
    st.rules.append({"id": did, "kind": d["kind"], "pattern": d["pattern"], "scope": d.get("scope", "all"),
                     "add_to_list": bool(d.get("add_to_list")), "note": d.get("note", ""),
                     "approved": now(), "approved_by": who})
    learnstate.save_rules(st, ld)
    cur["state"] = "승인"
    stt[did] = cur
    wjson(ld / "proposals/status.json", stt)
    history(ld, "approve", id=did, who=who, fixed_requests=cur.get("fixed_requests"))
    return "적용했습니다."


def reject_draft(did: str, ld: Path | None = None) -> str:
    ld = ld or learnstate.learn_dir()
    stt = load_status(ld)
    cur = stt.get(did, {})
    cur["state"] = "거절"
    stt[did] = cur
    wjson(ld / "proposals/status.json", stt)
    history(ld, "reject", id=did)
    return "거절했습니다."


# ---------------------------------------------------------------- 주간 보고
def report(ld: Path | None = None, days: int = 7, today: dt.date | None = None) -> Path:
    ld = ld or learnstate.learn_dir()
    today = today or dt.date.today()
    since = dt.datetime.combine(today - dt.timedelta(days=days), dt.time()).astimezone()
    ev = []
    hp = ld / "history.jsonl"
    if hp.exists():
        for ln in hp.read_text(encoding="utf-8").splitlines():
            e = json.loads(ln)
            if dt.datetime.fromisoformat(e["ts"]) >= since:
                ev.append(e)
    miss = sum(e["miss"] for e in ev if e["event"] == "marks")
    over = sum(e["over"] for e in ev if e["event"] == "marks")
    docs = len({e["doc_id"] for e in ev if e["event"] == "marks"})
    auto = [i for e in ev if e["event"] in ("auto_apply", "word_approve") for i in (e.get("items") or [e.get("item")])]
    held = [e for e in ev if e["event"] == "hold"]
    stt = load_status(ld)
    waiting = [k for k, v in stt.items() if v.get("state") == "검사 통과"]
    failed = [k for k, v in stt.items() if v.get("state") == "검사 실패"]
    untouched = [p.stem for p in drafts(ld) if p.stem not in stt]
    reqs = sorted(p.stem for p in (ld / "proposals/requests").glob("*.json"))
    drafted = set()
    for p in drafts(ld):
        d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        drafted |= set(d.get("request_ids") or [])
    open_reqs = [q for q in reqs if q not in drafted]
    approved = [e["id"] for e in ev if e["event"] == "approve"]
    lines = [f"# 오답 노트 주간 보고 ({(today - dt.timedelta(days=days)).isoformat()} ~ {today.isoformat()})", "",
             "이 파일은 발송하지 않는다. 진짜 값은 넣지 않았다.", "",
             f"- 검수 표시: 문서 {docs}건, 놓침 {miss}건, 잘못 가림 {over}건",
             f"- 자동 반영한 낱말 {len(auto)}개", *[f"  - {a}" for a in auto],
             f"- 보류 {len(held)}건", *[f"  - {h.get('item')}: {'; '.join(h.get('why') or [])}" for h in held],
             f"- 승인 대기 수정안 {len(waiting)}건(회귀 시험 통과): {', '.join(waiting) or '없음'}",
             f"- 검사 실패 수정안 {len(failed)}건: {', '.join(failed) or '없음'}",
             f"- 아직 검사하지 않은 수정안 {len(untouched)}건: {', '.join(untouched) or '없음'}",
             f"- 이번 주 승인한 수정안 {len(approved)}건: {', '.join(approved) or '없음'}",
             f"- 수정안이 아직 없는 요청 {len(open_reqs)}건: {', '.join(open_reqs) or '없음'}",
             f"- 회귀 세트 사례 누적 {len(case_files(ld))}건", ""]
    out = ld / "reports" / f"주간보고-{today.isoformat()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# ---------------------------------------------------------------- 회귀 기준
def init_base(run: Path, fake: Path, dest: Path = BASE_DIR):
    if (dest / "meta.json").exists():
        sys.exit(f"이미 회귀 기준이 있습니다: {dest} (덮어쓰지 않습니다)")
    (dest / "texts").mkdir(parents=True, exist_ok=True)
    (dest / "answers").mkdir(parents=True, exist_ok=True)
    (dest / "src").mkdir(parents=True, exist_ok=True)
    meta = []
    for mf in sorted((run / "secure/maps").glob("*.map.json")):
        mp = json.loads(mf.read_text(encoding="utf-8"))
        fn = mp["original_filename"]
        stem = Path(fn).stem
        doc = fn[:3]
        import evaluate
        fmt = evaluate.fmt_of(fn)
        shutil.copy2(run / "secure/work" / f"{mp['doc_id']}.md", dest / "texts" / f"{stem}.md")
        shutil.copy2(fake / "answers" / f"{doc}.answer.json", dest / "answers" / f"{doc}.answer.json")
        shutil.copy2(fake / "src" / f"{doc}.md", dest / "src" / f"{doc}.md")
        meta.append({"file": stem, "doc": doc, "fmt": fmt, "source_type": mp["source_type"],
                     "profile": mp.get("profile", "fixed"), "ner": mp.get("ner", True)})
    wjson(dest / "meta.json", meta)
    print(f"회귀 기준 {len(meta)}건을 만들었습니다: {dest}")


def status(ld: Path | None = None):
    ld = ld or learnstate.learn_dir()
    st = learnstate.load(ld)
    print(f"학습 폴더: {ld}")
    print(f"라벨 {json.dumps(st.labels, ensure_ascii=False)}")
    print(f"예외 낱말 {st.exceptions}")
    print(f"오독 글자 {st.confusions}")
    print(f"승인된 규칙 {[r['id'] for r in st.rules]}")
    print(f"회귀 사례 {len(case_files(ld))}건, 요청 {len(list((ld / 'proposals/requests').glob('*.json')))}건, "
          f"수정안 {len(drafts(ld))}건")
    for k, v in load_status(ld).items():
        print(f"  {k}: {v.get('state')} {'; '.join(v.get('reasons') or [])}")


def main():
    ap = argparse.ArgumentParser(description="오답 노트")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("ingest", "words"):
        p = sub.add_parser(name)
        p.add_argument("--out", default=str(ROOT))
    for name in ("approve-word", "reject-word"):
        p = sub.add_parser(name)
        p.add_argument("n", type=int)
        p.add_argument("--out", default=str(ROOT))
    for name in ("check", "approve", "reject"):
        p = sub.add_parser(name)
        p.add_argument("draft_id")
        if name == "approve":
            p.add_argument("--who", default="직원")
    p = sub.add_parser("report")
    p.add_argument("--days", type=int, default=7)
    sub.add_parser("status")
    p = sub.add_parser("init-base")
    p.add_argument("--from", dest="src", required=True)
    p.add_argument("--fake", default=str(ROOT / "tests/fake"))
    a = ap.parse_args()
    import netguard
    netguard.install(str(ROOT / "logs/netguard.log"))
    if a.cmd == "ingest":
        ingest(Path(a.out).resolve())
    elif a.cmd == "words":
        for w in words(Path(a.out).resolve()):
            print(f"{w['n']}. [{w['status']}] {w['word']} ({w['doc_id']})")
    elif a.cmd in ("approve-word", "reject-word"):
        print(decide_word(Path(a.out).resolve(), a.n, a.cmd == "approve-word"))
    elif a.cmd == "check":
        r = check_draft(a.draft_id)
        print(r["state"], "; ".join(r["reasons"]), json.dumps(r["gate"], ensure_ascii=False))
    elif a.cmd == "approve":
        print(approve_draft(a.draft_id, who=a.who))
    elif a.cmd == "reject":
        print(reject_draft(a.draft_id))
    elif a.cmd == "report":
        print(report(days=a.days))
    elif a.cmd == "status":
        status()
    elif a.cmd == "init-base":
        init_base(Path(a.src).resolve(), Path(a.fake).resolve())


if __name__ == "__main__":
    main()
