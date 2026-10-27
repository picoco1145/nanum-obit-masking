"""오답 노트가 고친 설정을 읽고 처리 단계에 끼워 넣는다.

학습 폴더(기본 learn/, 환경 변수 NANUM_LEARN_DIR로 바꿈)에는 진짜 값이 들어가지 않는다.
- learned.yaml     : 사람 승인 없이 자동 반영하는 낱말 목록(라벨·예외 낱말·OCR 오독 글자)
- rules_extra.yaml : 직원이 승인한 정규식 규칙(Claude Code가 가짜화된 사례만 보고 쓴 수정안)
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
KDIGIT = {"공": "0", "영": "0", "빵": "0", "일": "1", "이": "2", "삼": "3", "사": "4",
          "오": "5", "육": "6", "륙": "6", "칠": "7", "팔": "8", "구": "9"}
EMPTY_LEARNED = {"version": 1, "labels": {}, "exceptions": [], "ocr_confusions": {}}
EMPTY_RULES = {"version": 1, "rules": []}


def learn_dir() -> Path:
    return Path(os.environ.get("NANUM_LEARN_DIR") or (ROOT / "learn")).resolve()


@dataclass
class LearnState:
    labels: dict = field(default_factory=dict)        # {NAME: {"": [라벨,...]}, ADDR: [라벨,...]}
    exceptions: list = field(default_factory=list)    # 이름이 아닌 낱말
    confusions: dict = field(default_factory=dict)    # 오독 글자 → 숫자 글자
    rules: list = field(default_factory=list)         # 승인된 정규식 규칙

    def key(self) -> str:
        blob = json.dumps([self.labels, sorted(self.exceptions), self.confusions, self.rules],
                          ensure_ascii=False, sort_keys=True)
        return hashlib.sha1(blob.encode()).hexdigest()[:12]

    def copy(self) -> "LearnState":
        return copy.deepcopy(self)

    def compiled_rules(self):
        out = []
        for r in self.rules:
            try:
                out.append((r, re.compile(r["pattern"], re.M)))
            except re.error:
                continue
        return out


def load(d: Path | None = None) -> LearnState:
    d = d or learn_dir()
    lp, rp = d / "learned.yaml", d / "rules_extra.yaml"
    ld = yaml.safe_load(lp.read_text(encoding="utf-8")) if lp.exists() else EMPTY_LEARNED
    rd = yaml.safe_load(rp.read_text(encoding="utf-8")) if rp.exists() else EMPTY_RULES
    ld = ld or EMPTY_LEARNED
    rd = rd or EMPTY_RULES
    return LearnState(ld.get("labels") or {}, list(ld.get("exceptions") or []),
                      dict(ld.get("ocr_confusions") or {}), list(rd.get("rules") or []))


def save_learned(st: LearnState, d: Path | None = None):
    d = d or learn_dir()
    d.mkdir(parents=True, exist_ok=True)
    body = {"version": 1, "labels": st.labels, "exceptions": sorted(set(st.exceptions)),
            "ocr_confusions": st.confusions}
    head = ("# 오답 노트가 자동으로 더한 낱말 목록이다. 진짜 값은 넣지 않는다.\n"
            "# labels: 새 칸 이름, exceptions: 이름이 아닌 낱말, ocr_confusions: OCR 오독 글자 → 숫자 글자\n")
    (d / "learned.yaml").write_text(head + yaml.safe_dump(body, allow_unicode=True, sort_keys=False),
                                    encoding="utf-8")


def save_rules(st: LearnState, d: Path | None = None):
    d = d or learn_dir()
    d.mkdir(parents=True, exist_ok=True)
    head = ("# 직원이 승인한 정규식 규칙이다. learn.py approve가 덧붙인다. 손으로 고치지 않는다.\n"
            "# kind: NAME/RRN/PHONE/ADDR, pattern: 그룹 n이 있으면 그 부분만 가린다, scope: all 또는 ocr\n")
    (d / "rules_extra.yaml").write_text(head + yaml.safe_dump({"version": 1, "rules": st.rules},
                                                              allow_unicode=True, sort_keys=False),
                                        encoding="utf-8")


# ---------------------------------------------------------------- OCR 오독 글자 바로잡기
def normalize(text: str, conf: dict) -> str:
    """숫자 사이에 낀 오독 글자를 숫자 글자로 바꾼다. 글자 수는 그대로라 위치가 바뀌지 않는다.

    바꾸는 조건: 숫자·한글 숫자·오독 글자·구분자가 이어진 구간에서, 바꾼 뒤 숫자로 볼 글자가 7개 이상이고
    오독 글자가 그 3분의 1 이하일 때만 바꾼다(보통 낱말 속 글자는 건드리지 않는다).
    """
    if not conf:
        return text
    keys = "".join(re.escape(k) for k in conf)
    run = re.compile(rf"[0-9{''.join(KDIGIT)}{keys}][0-9{''.join(KDIGIT)}{keys}\- .]*")
    chars = list(text)
    for m in run.finditer(text):
        seg = m.group(0)
        bad = [i for i, c in enumerate(seg) if c in conf]
        if not bad:
            continue
        digitish = sum(1 for c in seg if c.isdigit() or c in KDIGIT or c in conf)
        if digitish < 7 or len(bad) > max(1, digitish // 3):
            continue
        for i in bad:
            chars[m.start() + i] = conf[seg[i]]
    return "".join(chars)


def extra_label_block(st: LearnState) -> dict:
    return st.labels or {}


def is_exception(word: str, st: LearnState) -> bool:
    w = re.sub(r"\s+", "", word)
    return bool(w) and w in set(st.exceptions)


def extra_rule_hits(text: str, st: LearnState, ocr: bool):
    """승인된 규칙이 잡은 구간: [(start, end, kind, rule_id, add_to_list)]"""
    out = []
    for r, rx in st.compiled_rules():
        if r.get("scope") == "ocr" and not ocr:
            continue
        for m in rx.finditer(text):
            if "n" in rx.groupindex and m.group("n") is not None:
                s, e = m.start("n"), m.end("n")
            else:
                s, e = m.start(), m.end()
            if e > s:
                out.append((s, e, r["kind"], r.get("id", "extra"), bool(r.get("add_to_list"))))
    return out
