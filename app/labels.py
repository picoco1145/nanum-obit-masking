"""라벨 칸 읽기(지시서 5절 ③)와 문서 명단을 문서 전체에 적용하기(지시서 8절)."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import rules

HANGUL = "가-힣"
TWO_CHAR_SURNAMES = ["남궁", "선우", "제갈", "황보", "독고", "사공", "서문"]
SURNAMES = set(
    "김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 전 홍 유 고 문 양 손 배 백 허 남 심 노 하 곽 성 차 주 "
    "우 구 민 류 나 진 지 엄 채 원 천 방 공 현 함 변 염 여 추 도 소 석 선 설 마 길 연 위 표 명 기 반 라 왕 금 옥 육 "
    "인 맹 제 모 탁 국 어 은 편 용 예 경 봉 사 부 황 가 복 태 목 형 피 두 감 음 빈 동 온 호 범 좌 팽 승 간 상 시 갈 "
    "단 견 당 화 창 옹 순 빙 리".split()
) | set(TWO_CHAR_SURNAMES)
NOT_NAME = {"미상", "없음", "무연고", "해당없음", "불명", "같음", "동일", "상동", "본인", "남", "여",
            "공영장례", "장례", "발생", "지원", "요청", "통보", "처리", "인수", "확인", "현황", "명단", "인적사항",
            "사항", "관련", "시신", "안치", "의뢰", "협조", "결과", "장례식", "무연고사망자"}
# 이름이 아닌 것으로 보는 낱말(직함·관계·결재 용어). 실험에서 오탐이 나오면 여기에 더한다.
TITLE_WORDS = {
    "주무관", "사회복지주무관", "팀장", "과장", "국장", "소장", "관리소장", "관리인", "순경", "경위", "경사", "경장",
    "주민", "이웃", "직원", "동료", "장남", "차남", "장녀", "차녀", "아들", "딸", "배우자", "조카", "손자", "손녀",
    "형", "동생", "누나", "오빠", "언니", "부친", "모친", "전결", "대결", "직인", "생략", "담당", "담당자", "협조자",
    "기안자", "검토자", "공동주택", "원룸", "고시원", "아파트", "빌라", "이장", "통장", "반장", "영사", "복지정책과장",
    "사회복지팀장", "희망복지지원단", "맞춤형복지팀", "희망복지팀", "연락처", "전화", "전송", "성별", "나이",
}
ORG_SUFFIX = ("구청", "센터", "지원단", "경찰서", "병원", "복지팀", "과장", "팀장", "주민센터", "사무소", "구", "시", "군", "과", "팀", "단")
PREFIX_STRIP = re.compile(r"^(故\s*|고\s+|망\s+)")


def norm_label(s: str) -> str:
    s = html.unescape(s)
    s = re.sub(r"[\s:：·ㆍ\.\-]", "", s)
    return s.strip("*")


@dataclass
class Cell:
    table: int
    row: int
    col: int
    colspan: int
    start: int
    end: int
    text: str


@dataclass
class Entry:
    kind: str          # NAME / RRN / PHONE / ADDR / ORG_PHONE / ORG_ADDR
    value: str
    role: str
    source: str        # label / ner
    hanja: str | None = None
    spans: list[tuple[int, int]] = field(default_factory=list)


class LabelDict:
    def __init__(self, path: Path, text: str, extra: dict | None = None):
        cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.map: dict[str, tuple[str, str]] = {}
        self._add(cfg["common"])
        if extra:
            self._add(extra)        # 오답 노트가 더한 칸 이름(learn/learned.yaml)
        for form in cfg.get("forms") or []:
            if any(k in text for k in form.get("match_any", [])):
                self._add(form.get("extra", {}))
        keys = sorted(self.map, key=len, reverse=True)
        self.raw_keys = keys

    def _add(self, block):
        for kind, v in block.items():
            if isinstance(v, dict):
                for role, labels in v.items():
                    for lb in labels:
                        self.map[norm_label(lb)] = (kind, role)
            else:
                for lb in v:
                    self.map[norm_label(lb)] = (kind, "")

    def lookup(self, cell_text: str):
        n = norm_label(cell_text)
        if not n:
            return None
        if n in self.map:
            return self.map[n]
        base = re.sub(r"\(.*?\)", "", n)
        if base and base in self.map:
            kind, role = self.map[base]
            return kind, role
        return None


# ---------------------------------------------------------------- 표 읽기
CELL_RE = re.compile(r"<(td|th)([^>]*)>(.*?)</\1>", re.S)


def parse_tables(text: str) -> list[list[Cell]]:
    tables: list[list[Cell]] = []
    # HTML 표
    for tm in re.finditer(r"<table[^>]*>(.*?)</table>", text, re.S):
        cells = []
        ti = len(tables)
        for ri, rm in enumerate(re.finditer(r"<tr[^>]*>(.*?)</tr>", tm.group(0), re.S)):
            col = 0
            base = tm.start() + rm.start(1)
            for cm in CELL_RE.finditer(rm.group(1)):
                span = re.search(r'colspan="?(\d+)', cm.group(2))
                cs = int(span.group(1)) if span else 1
                s, e = base + cm.start(3), base + cm.end(3)
                s, e = _trim(text, s, e)
                cells.append(Cell(ti, ri, col, cs, s, e, text[s:e]))
                col += cs
        tables.append(cells)
    # 마크다운 파이프 표 (방법 B의 OCR 행 포함)
    lines = text.split("\n")
    pos = 0
    cur: list[Cell] | None = None
    row = 0
    for ln in lines:
        st = ln.strip()
        if st.startswith("|") and st.count("|") >= 2:
            if re.fullmatch(r"\|[\s\-:|]+\|?", st):
                pos += len(ln) + 1
                continue
            if cur is None:
                cur = []
                row = 0
            ti = len(tables)
            bars = [m.start() for m in re.finditer(r"(?<!\\)\|", ln)]
            for ci in range(len(bars) - 1):
                s, e = _trim(text, pos + bars[ci] + 1, pos + bars[ci + 1])
                cur.append(Cell(ti, row, ci, 1, s, e, text[s:e]))
            row += 1
        else:
            if cur is not None:
                tables.append(cur)
                cur = None
        pos += len(ln) + 1
    if cur is not None:
        tables.append(cur)
    return tables


def _trim(text, s, e):
    while s < e and text[s] in " \t\n":
        s += 1
    while e > s and text[e - 1] in " \t\n":
        e -= 1
    return s, e


def table_ranges(text: str) -> list[tuple[int, int]]:
    out = [(m.start(), m.end()) for m in re.finditer(r"<table[^>]*>.*?</table>", text, re.S)]
    pos = 0
    for ln in text.split("\n"):
        if ln.strip().startswith("|"):
            out.append((pos, pos + len(ln)))
        pos += len(ln) + 1
    return out


# ---------------------------------------------------------------- 값에서 이름 뽑기
def split_name(name: str) -> tuple[str, str]:
    for s in TWO_CHAR_SURNAMES:
        if name.startswith(s) and len(name) >= 3:
            return s, name[2:]
    return name[:1], name[1:]


def _is_name_token(tok: str) -> bool:
    if tok in NOT_NAME or tok in TITLE_WORDS:
        return False
    if all(c in rules.KDIGIT for c in tok):      # '공일공' 같은 한글 숫자
        return False
    if not (2 <= len(tok) <= 5):
        return False
    if tok[:2] in TWO_CHAR_SURNAMES:
        return True
    return tok[0] in SURNAMES


def _strip_josa(t: str) -> str:
    """'김철수씨는', '연락처는' 같은 낱말에서 뒤에 붙은 호칭·조사를 뗀다."""
    m = re.match(r"^(.+?)(님은|씨는|님의|씨의|님이|씨가|씨에게|님께서|님|씨|에게|께서|은|는|을|를|의|이|가)$", t)
    if m and len(m.group(1)) >= 2 and (len(t) >= 4 or m.group(2) not in ("이", "가", "은")):
        base = m.group(1)
        if base in TITLE_WORDS or base in NOT_NAME:
            return ""
        return base
    return t


def names_from_value(value: str, free_text: bool = False) -> list[tuple[str, int, int, str | None]]:
    """값에서 (이름, 시작, 끝, 한자)를 뽑는다. 위치는 value 기준."""
    out = []
    v = html.unescape(value)
    # 괄호 속 한자를 한자 이름으로 따로 본다
    hanja = None
    hm = re.search(r"\(([\u4e00-\u9fff]{2,5})\)", v)
    if hm:
        hanja = hm.group(1)
    # 괄호 설명은 같은 길이의 공백으로 바꿔 위치를 유지한다
    masked = re.sub(r"\([^)]*\)", lambda m: " " * len(m.group(0)), v)
    parts = [(m.start(), m.group(0)) for m in re.finditer(r"[^,·/]+", masked)]
    for pstart, part in parts:
        # '및'으로도 나눈다
        for sub in re.finditer(r"(?:(?!\s및\s).)+", part):
            seg = sub.group(0)
            sstart = pstart + sub.start()
            toks = [(m.start() + sstart, m.group(0)) for m in re.finditer(rf"(?<![0-9])[{HANGUL}]+", seg)]
            toks = [(s, PREFIX_STRIP.sub("", t)) if t in ("故", "고", "망") else (s, t) for s, t in toks]
            toks = [(s, t) for s, t in toks if t not in ("고", "망", "님", "씨")]
            # 한 글자씩 띄어 쓴 이름(진 동 철)
            if toks and all(len(t) == 1 for _, t in toks) and 2 <= len(toks) <= 5:
                name = "".join(t for _, t in toks)
                if _is_name_token(name):
                    out.append((name, toks[0][0], toks[-1][0] + 1, hanja))
                continue
            # 호칭·조사 떼기
            clean = [(s, _strip_josa(t)) for s, t in toks]
            clean = [(s, t) for s, t in clean if t]
            picked = []
            if len(clean) == 1 and 2 <= len(clean[0][1]) <= 5 and clean[0][1] not in NOT_NAME \
                    and clean[0][1] not in TITLE_WORDS and not all(c in rules.KDIGIT for c in clean[0][1]):
                picked.append(clean[0])          # 값이 낱말 하나면 그대로 이름으로 본다(외국인 이름 포함)
            else:
                if clean and _is_name_token(clean[0][1]) and not (len(clean[0][1]) >= 3 and clean[0][1].endswith(ORG_SUFFIX)):
                    picked.append(clean[0])
                for i in range(1, len(clean)):
                    prev = clean[i - 1][1]
                    if (prev in TITLE_WORDS or prev.endswith(("주무관", "팀장", "과장", "관리인", "소장", "순경"))) \
                            and _is_name_token(clean[i][1]) and clean[i] not in picked:
                        picked.append(clean[i])
            if not picked and not free_text:
                for s, t in clean:
                    if _is_name_token(t) and not t.endswith(ORG_SUFFIX):
                        picked.append((s, t))
                        break
            for s, t in picked:
                out.append((t, s, s + len(t), hanja))
    return out


# ---------------------------------------------------------------- 라벨 칸 → 문서 명단
def build_list(text: str, ld: LabelDict, fix: bool, policy: dict) -> list[Entry]:
    entries: list[Entry] = []
    tables = parse_tables(text)
    for cells in tables:
        grid = {}
        for c in cells:
            grid[(c.row, c.col)] = c
        by_row: dict[int, list[Cell]] = {}
        for c in cells:
            by_row.setdefault(c.row, []).append(c)
        for c in cells:
            hit = ld.lookup(c.text)
            if not hit:
                continue
            kind, role = hit
            row_cells = sorted(by_row[c.row], key=lambda x: x.col)
            right = next((x for x in row_cells if x.col == c.col + c.colspan), None)
            label_cnt = sum(1 for x in row_cells if ld.lookup(x.text))
            values: list[Cell] = []
            header_mode = False
            if fix:
                # 고친 방식: 한 행에 라벨이 여럿이고 바로 아래 칸이 라벨이 아니면 머리 행(열 방향)으로 본다
                below = grid.get((c.row + 1, c.col))
                if label_cnt >= 3 and below is not None and not ld.lookup(below.text):
                    header_mode = True
                elif right is not None and not ld.lookup(right.text):
                    values = [right]
                elif right is None or ld.lookup(right.text):
                    header_mode = c.row == min(by_row)
            else:
                # 지시서 그대로: 오른쪽 칸이 있으면 값, 없고 머리 행이면 아래 칸들
                if right is not None:
                    values = [right]
                elif c.row == min(by_row):
                    header_mode = True
            if header_mode:
                values = [x for x in cells if x.col == c.col and x.row > c.row]
            for v in values:
                r = role
                if header_mode and fix and kind == "NAME":
                    first = min(by_row.get(v.row, [v]), key=lambda x: x.col)
                    fh = ld.lookup(first.text) if first is not v else None
                    if fh and fh[0] == "NAME":
                        r = fh[1]
                _add_value(entries, kind, r, v.text, v.start, fix, policy, ld=ld)
    # 표 밖의 "라벨 + 구분자 + 값"
    tr = table_ranges(text)
    lab_alt = "|".join(re.escape(k) for k in sorted(set(_raw_labels(ld)), key=len, reverse=True))
    lab_re = re.compile(rf"(?<![{HANGUL}A-Za-z])({lab_alt})(?:\s*\([^)\n]{{0,12}}\))?(?=\s*[:：]|\s|$|\()")
    pos = 0
    for ln in text.split("\n"):
        ls = pos
        pos += len(ln) + 1
        if any(a <= ls < b for a, b in tr):
            continue
        ms = list(lab_re.finditer(ln))
        for i, m in enumerate(ms):
            hit = ld.lookup(m.group(1))
            if not hit:
                continue
            kind, role = hit
            vs = m.end()
            ve = ms[i + 1].start() if i + 1 < len(ms) else len(ln)
            seg = ln[vs:ve]
            lead = len(seg) - len(seg.lstrip(" :：\t"))
            _add_value(entries, kind, role, seg[lead:].rstrip(), ls + vs + lead, fix, policy, free_text=True, ld=ld)
    return entries


def _raw_labels(ld: LabelDict):
    # 사전의 정규화 키를 그대로 쓰되, 공백이 들어간 원문 표기(성 명)는 표에서만 나온다
    return ld.map.keys()


def is_label_word(word: str, ld: "LabelDict") -> bool:
    """라벨 사전에 있는 낱말(고인·신고인 등)이거나 그것으로 끝나는 낱말(가고인)은 이름이 아니다."""
    n = norm_label(word)
    return any(n == k or (len(k) >= 2 and n.endswith(k)) for k in ld.map)


def _add_value(entries, kind, role, value, vstart, fix, policy, free_text=False, ld=None):
    if not value.strip():
        return
    if kind == "NAME":
        if role == "담당공무원" and not policy.get("mask_officials", True):
            return
        for name, s, e, hanja in names_from_value(value, free_text):
            if fix and ld is not None and is_label_word(name, ld):
                continue
            if free_text and s > 25:
                # 문장 속 라벨은 라벨 바로 뒤 이름만 본다
                continue
            entries.append(Entry("NAME", name, role, "label", hanja, [(vstart + s, vstart + e)]))
    elif kind in ("RRN", "PHONE", "ORG_PHONE"):
        for s, e in rules.find_in_value(value, kind, fix):
            k = kind
            if kind == "ORG_PHONE" and not policy.get("mask_org_contact", True):
                continue
            entries.append(Entry(k, value[s:e], role, "label", None, [(vstart + s, vstart + e)]))
    elif kind == "ADDR":
        v = value.strip()
        if not re.search(r"\d", v) or not re.search(r"(로|길|동|리|번지|구|시|군|읍|면)", v):
            return
        if free_text:
            # 문장 속에서는 주소 정규식이 잡은 범위만 쓴다
            m = re.search(rules.ADDR_FULL, v) or re.search(rules.ADDR_NOSIDO, v)
            if not m:
                return
            v = v[m.start():m.end()].rstrip(" ,")
            off = value.find(v)
        else:
            off = value.find(v)
        entries.append(Entry("ADDR", v, role, "label", None, [(vstart + off, vstart + off + len(v))]))


# ---------------------------------------------------------------- 명단을 문서 전체에 적용
JOSA_NEXT = "은는이가을를의에께와과도만님씨군양으로라"
SEPCH = r"[\s\-–—~ㅡ.()\\]*"


def name_variants(name: str, hanja: str | None, fix: bool) -> list[tuple[str, str, bool]]:
    """(정규식, 변형 이름, 검수필요) 목록. 정규식의 그룹 'n'이 가릴 부분이다."""
    out = []
    sp = r"[ \t]*"
    full = sp.join(re.escape(c) for c in name)
    left = rf"(?:(?<![{HANGUL}])|(?<=[고망故]))"
    right = rf"(?=[^{HANGUL}]|$|[{JOSA_NEXT}])"
    out.append((rf"{left}(?P<n>{full}){right}", "full", False))
    sur, given = split_name(name)
    if len(given) >= 2:
        g = sp.join(re.escape(c) for c in given)
        out.append((rf"(?<![{HANGUL}])(?P<n>{g})(?=[ \t]?(?:씨|님|군|양|이가|이는|이를|이의|이에게)|[은는을를의가와])", "given", True))
    out.append((rf"(?<![{HANGUL}])(?P<n>{re.escape(sur)})(?=[ \t]?씨)", "surname", True))
    if len(name) >= 3:
        for i in range(len(name)):
            pat = sp.join((rf"(?!{re.escape(c)})[{HANGUL}]" if j == i else re.escape(c)) for j, c in enumerate(name))
            out.append((rf"(?<![{HANGUL}])(?P<n>{pat})(?=[^{HANGUL}]|$|[{JOSA_NEXT}])", "ocr1", True))
    if hanja:
        out.append((rf"(?P<n>{re.escape(hanja)})", "hanja", False))
    return out


def number_pattern(value: str) -> str | None:
    chars = []
    for c in value:
        if c.isdigit():
            chars.append(c)
        elif c in rules.KDIGIT:
            chars.append(rules.KDIGIT[c])
        elif c in "*xX●○#":
            chars.append("*")
    if sum(ch.isdigit() for ch in chars) < 6:
        return None
    rev = {}
    for k, d in rules.KDIGIT.items():
        rev.setdefault(d, []).append(k)
    parts = []
    for ch in chars:
        if ch == "*":
            parts.append(r"\\?[*xX●○#\d]")
        else:
            parts.append("[" + ch + "".join(rev.get(ch, [])) + "]")
    return r"(?<![\d])" + SEPCH.join(parts) + r"(?![\d*])"


def addr_pattern(value: str) -> str:
    chars = [c for c in value if not c.isspace()]
    return r"\s*".join(re.escape(c) for c in chars)


@dataclass
class Span:
    start: int
    end: int
    kind: str
    source: str        # label / list / rule / ner
    key: str           # 명단 값(이름) 또는 규칙 이름
    review: bool
    reason: str
    role: str = ""


def apply_list(text: str, entries: list[Entry], fix: bool) -> list[Span]:
    spans: list[Span] = []
    for en in entries:
        for s, e in en.spans:
            spans.append(Span(s, e, en.kind, "label" if en.source == "label" else en.source, en.value,
                              en.source == "ner", "NER" if en.source == "ner" else "", en.role))
        if en.kind == "NAME":
            for pat, var, rv in name_variants(en.value, en.hanja, fix):
                for m in re.finditer(pat, text):
                    spans.append(Span(m.start("n"), m.end("n"), "NAME", "list", en.value, rv or en.source == "ner",
                                      var if rv else ("NER" if en.source == "ner" else ""), en.role))
        elif en.kind in ("RRN", "PHONE", "ORG_PHONE"):
            pat = number_pattern(en.value)
            if pat:
                for m in re.finditer(pat, text):
                    spans.append(Span(m.start(), m.end(), en.kind, "list", en.value, False, "", en.role))
        elif en.kind in ("ADDR", "ORG_ADDR"):
            for m in re.finditer(addr_pattern(en.value), text):
                spans.append(Span(m.start(), m.end(), en.kind, "list", en.value, False, "", en.role))
    return spans
