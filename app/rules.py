"""정규식 규칙 (지시서 7절).

FIX 플래그가 켜지면 시제품 실험에서 찾은 문제를 고친 정규식을 쓴다.
꺼져 있으면 지시서에 적힌 정규식을 그대로 쓴다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- 7.1 주민등록번호
SEP = r"\s*[-–—~ㅡ]?\s*"
YYMMDD = r"\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
BACK1 = r"[1-8]"   # 지시서: 외국인등록번호까지 기본값 [1-8]


def rrn_patterns(fix: bool) -> list[tuple[str, str]]:
    # fix: kordoc 마크다운 표는 *를 \*로 바꿔 내보내므로 역슬래시를 허용한다
    maskch = r"(?:\\?[\d*xX●○#])" if fix else r"[\d*xX●○#]"
    star = r"(?:\\?[*xX●])" if fix else r"[*xX●]"
    return [
        ("RRN_FULL", rf"(?<!\d){YYMMDD}{SEP}{BACK1}\d{{6}}(?!\d)"),
        ("RRN_BACK_HID", rf"(?<!\d){YYMMDD}{SEP}{BACK1}{maskch}{{6}}(?![\d*])"),
        ("RRN_ALL_HID", rf"(?<!\d){YYMMDD}\s*[-–—]\s*{star}{{7}}"),
        ("RRN_FRONT_HID", rf"{star}{{6}}\s*[-–—]\s*{BACK1}\d{{6}}(?!\d)"),
    ]


# ---------------------------------------------------------------- 7.2 전화번호
D = r"[\d*xX]"
S = r"\s*[-.)\s]?\s*"
PHONE_PATTERNS = [
    ("MOBILE", rf"(?<!\d)01[016789]{S}{D}{{3,4}}{S}{D}{{4}}(?!\d)"),
    ("LANDLINE", rf"(?<!\d)\(?0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])\)?\s*[-.)\s]\s*{D}{{3,4}}\s*[-.\s]\s*{D}{{4}}(?!\d)"),
    ("VOIP", rf"(?<!\d)0(?:70|50\d){S}{D}{{3,4}}{S}{D}{{4}}(?!\d)"),
    ("INTL", rf"\+82\s*[-]?\s*\(?0?(?:1[016789]|2|[3-6]\d)\)?{S}\d{{3,4}}{S}\d{{4}}(?!\d)"),
    ("REP", rf"(?<!\d)1(?:5|6|8)\d{{2}}\s*[-.]\s*\d{{4}}(?!\d)"),
]
# fix: kordoc이 "(02) 123-4567"을 "(02)123-4567"로 붙여 내보낸다. 괄호 지역번호 뒤 구분자를 선택으로 둔다.
PHONE_FIX_EXTRA = [
    ("LANDLINE_PAREN", rf"(?<!\d)\(0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])\)\s*{D}{{3,4}}\s*[-.\s]\s*{D}{{4}}(?!\d)"),
]
# 라벨 칸 값 안에서는 구분자가 없어도 잡는다
PHONE_NOSEP = r"(?<!\d)(?:01[016789]\d{7,8}|0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])\d{7,8}|0(?:70|50\d)\d{7,8})(?!\d)"
PHONE_DIGITS_FULL = re.compile(r"^(?:01[016789]\d{7,8}|0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])\d{7,8}|0(?:70|50\d)\d{7,8})$")

# ---------------------------------------------------------------- 7.3 한글 숫자
KDIGIT = {"공": "0", "영": "0", "빵": "0", "일": "1", "이": "2", "삼": "3", "사": "4",
          "오": "5", "육": "6", "륙": "6", "칠": "7", "팔": "8", "구": "9"}
KRUN = re.compile(r"[공영빵일이삼사오육륙칠팔구0-9][공영빵일이삼사오육륙칠팔구0-9 \-.]*")

# ---------------------------------------------------------------- 7.4 주소
SIDO = (r"(?:서울특별시|서울시|서울|부산광역시|부산시|부산|대구광역시|대구|인천광역시|인천|"
        r"광주광역시|광주|대전광역시|대전|울산광역시|울산|세종특별자치시|세종시|세종|"
        r"경기도|경기|강원특별자치도|강원도|강원|충청북도|충북|충청남도|충남|"
        r"전북특별자치도|전라북도|전북|전라남도|전남|경상북도|경북|경상남도|경남|"
        r"제주특별자치도|제주도|제주)")
SIGUNGU = r"(?:[가-힣]{1,5}(?:시|군|구)\s*){1,2}"
EMD = r"(?:[가-힣0-9]{1,8}(?:읍|면)\s*)?"
ROAD = r"[가-힣0-9·]{1,15}(?:로|길)(?:\s*\d{1,4}번?(?:길|가길))?\s*\d{1,5}(?:-\d{1,5})?"
JIBUN = r"[가-힣0-9·]{1,10}(?:동|가|리)\s*(?:산\s*)?\d{1,5}(?:-\d{1,5})?(?:번지)?"
DETAIL = r"(?:\s*,?\s*(?:\d{1,4}\s*동)?\s*(?:\d{1,5}\s*호|\d{1,3}\s*층)?(?:\s*\([^)\n]{1,30}\))?)?"
ADDR_FULL = SIDO + r"\s*" + SIGUNGU + EMD + "(?:" + ROAD + "|" + JIBUN + ")" + DETAIL
ADDR_NOSIDO = SIGUNGU + EMD + "(?:" + ROAD + "|" + JIBUN + ")" + DETAIL
# fix: OCR이 "가상구샘플동"처럼 띄어쓰기를 지우면 SIGUNGU 뒤에 공백이 없어도 되도록 이미 \s*로 되어 있다.
ADDR_CONTEXT_WORDS = ("주소", "거주", "주거지", "사망장소", "소재")
# fix: 앞이 아니라 뒤에 '거주·살았·지냈·고시원·자택' 같은 말이 오는 경우도 주소로 본다
ADDR_CONTEXT_AFTER = ("거주", "살았", "지냈", "지낸", "고시원", "자택", "에서", "반지하", "숙소")

# ---------------------------------------------------------------- OCR 보정 (fixed 프로필 + 스캔·팩스에서만)
# 시제품 실험에서 OCR이 만든 변형을 보고 더한 규칙이다. 설계서에는 없다.
AREA = r"0(?:2|3[1-3]|4[1-4]|5[1-5]|6[1-4])"
OCR_RRN = [
    # kordoc이 *를 \*로 바꾸고 OCR이 별표 몇 개를 빠뜨린 경우: 450315-2\*\*\*\*
    ("OCR_RRN_STARS", rf"(?<!\d){YYMMDD}\s*[-–—]?\s*{BACK1}(?:\\?[*xX●#]){{2,6}}"),
    # 뒷자리 별표가 통째로 빠진 경우: 4803021
    ("OCR_RRN_7", rf"(?<![\d.]){YYMMDD}\s*[-–—]?\s*{BACK1}(?![\d.])"),
]
OCR_PHONE = [
    # ☎ 기호를 8로 읽은 경우: 802-2100-3456, 8032-7654321
    ("OCR_TEL8", rf"(?<!\d)8\s*{AREA}\s*[-.)\s]?\s*\d{{3,4}}\s*[-.\s]?\s*\d{{4}}(?!\d)"),
]
SIDO_OCR = r"(?:[가-힣]{1,3}(?:특별시|광역시|별시|역시|자치시|자치도))"
ADDR_OCR = [
    # 시·도 이름을 틀리게 읽은 경우(서율특별시, 시울특별시)
    ("OCR_ADDR_SIDO", SIDO_OCR + r"\s*" + SIGUNGU + EMD + "(?:" + ROAD + "|" + JIBUN + ")" + DETAIL),
    # 앞의 '주소' 라벨이 깨진 경우: 시군구 + 도로명 + 번호
    ("OCR_ADDR_ROAD", SIGUNGU + EMD + ROAD + DETAIL),
    # 부번이 있는 지번(생플동 123-4)은 문맥 없이도 주소로 본다
    ("OCR_ADDR_JIBUN", r"(?<![가-힣])[가-힣]{1,6}동\s*(?:산\s*)?\d{1,5}-\d{1,5}(?:번지)?"),
]


def korean_digit_hits_ocr(text: str) -> list[Hit]:
    """OCR이 한글 숫자 한두 글자를 틀리게 읽은 번호(공일공 일이삼사 오육철필, 공일금 오오오오 공일공일)."""
    hits = []
    for m in re.finditer(r"(?<![가-힣])[공영]\S{1,4}(?:\s+\S{2,5}){1,3}", text):
        toks = list(re.finditer(r"\S+", m.group(0)))
        best = None
        num = tot = 0
        for k, t in enumerate(toks):
            w = re.sub(r"(로|으로|입니다|이며|이고|번|으|입)$", "", t.group(0))
            n = sum(1 for c in w if c in KDIGIT or c.isdigit())
            if n < max(1, len(w) // 2):
                break
            num += n
            tot += len(w)
            if k >= 1 and num >= 8 and num / tot >= 0.7:
                best = m.start() + t.start() + len(w)
        if best and text[m.start():m.start() + 2] in ("공일", "영일", "공이", "공삼", "공사", "공오", "공육", "공칠", "공팔"):
            hits.append(Hit(m.start(), best, "PHONE", "OCR_KOREAN_DIGITS"))
    return hits


NUMLIKE = re.compile(r"[\d이일삼사오육칠팔구공영][\d이일삼사오육칠팔구공영\-. ()]{5,18}[\d이일삼사오육칠팔구공영]")


def ocr_number_remnants(text: str) -> list[Hit]:
    """OCR이 숫자를 빠뜨리거나 바꾼 전화번호 잔해(010-01이4455, 82107788, 8053-200-111).
    아라비아 숫자 7개 이상, 한글 숫자 2개 이하이고 0·80·82로 시작하면 번호로 본다. 날짜·사업자번호는 뺀다."""
    hits = []
    for m in NUMLIKE.finditer(text):
        seg = m.group(0)
        a = len(seg) - len(seg.lstrip("이일삼사오육칠팔구공영 .-()"))
        b = len(seg.rstrip("이일삼사오육칠팔구공영 .-()"))
        if b <= a:
            continue
        core = seg[a:b]
        s0 = m.start() + a
        if s0 > 0 and text[s0 - 1].isdigit():
            continue
        arabic = sum(c.isdigit() for c in core)
        kor = sum(c in KDIGIT for c in core)
        if arabic < 7 or kor > 2:
            continue
        d = "".join(KDIGIT.get(c, c) for c in core if c.isdigit() or c in KDIGIT)
        if not (d[0] == "0" or d[:2] in ("80", "82")):
            continue
        if re.search(r"\d{4}\s*[-.]\s*\d{1,2}\s*[-.]\s*\d{1,2}", core) or re.fullmatch(r"\d{3}-\d{2}-\d{5}", core):
            continue
        hits.append(Hit(s0, m.start() + b, "PHONE", "OCR_NUM_REMNANT"))
    return hits


ORG_LINE = re.compile(r"(전송|팩스|FAX|Fax|대표전화|☎|우\s*\d{5}|주무관|팀장|과장|담당)")


@dataclass
class Hit:
    start: int
    end: int
    kind: str      # RRN / PHONE / ADDR / ORG_PHONE / ORG_ADDR
    rule: str


def _line_bounds(text: str, pos: int) -> tuple[int, int]:
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return s, (len(text) if e < 0 else e)


def is_org_context(text: str, start: int, footer_start: int | None) -> bool:
    s, e = _line_bounds(text, start)
    line = text[s:e]
    if re.search(r"(전송|팩스|FAX|Fax|대표전화|우\s*\d{5})", line):
        return True
    if footer_start is not None and start >= footer_start and ORG_LINE.search(line):
        return True
    return False


def korean_digit_hits(text: str, fix: bool = False) -> list[Hit]:
    hits = []
    for m in KRUN.finditer(text):
        run = m.group(0)
        # 앞쪽은 공·영·0이 처음 나오는 곳부터 본다
        i = 0
        while i < len(run) and run[i] not in "공영빵0":
            i += 1
        if i >= len(run):
            continue
        toks = [(t.start() + i, t.end() + i) for t in re.finditer(r"\S+", run[i:])]
        best = None
        for k in range(len(toks), 0, -1):
            seg = run[toks[0][0]:toks[k - 1][1]]
            digits = "".join(KDIGIT.get(c, c) for c in seg if c in KDIGIT or c.isdigit())
            numeric_chars = sum(1 for c in seg if c in KDIGIT or c.isdigit())
            if numeric_chars < 9:
                break
            if 9 <= len(digits) <= 11 and PHONE_DIGITS_FULL.match(digits):
                # 순수 아라비아 숫자 번호는 일반 규칙이 맡는다
                if sum(c in KDIGIT for c in seg) >= (3 if fix else 1):
                    best = (toks[0][0], toks[k - 1][1])
                break
        if best:
            hits.append(Hit(m.start() + best[0], m.start() + best[1], "PHONE", "KOREAN_DIGITS"))
    return hits


def find_all(text: str, fix: bool, footer_start: int | None = None, ocr: bool = False) -> list[Hit]:
    hits: list[Hit] = []
    if fix and ocr:
        for name, pat in OCR_RRN:
            hits += [Hit(m.start(), m.end(), "RRN", name) for m in re.finditer(pat, text)]
        for name, pat in OCR_PHONE:
            for m in re.finditer(pat, text):
                kind = "ORG_PHONE" if is_org_context(text, m.start(), footer_start) else "PHONE"
                hits.append(Hit(m.start(), m.end(), kind, name))
        for name, pat in ADDR_OCR:
            for m in re.finditer(pat, text):
                s2, e2 = _line_bounds(text, m.start())
                kind = "ORG_ADDR" if re.search(r"우\s*\d{5}", text[s2:e2]) else "ADDR"
                hits.append(Hit(m.start(), _rstrip(text, m.start(), m.end()), kind, name))
        hits += korean_digit_hits_ocr(text)
        for h in ocr_number_remnants(text):
            if is_org_context(text, h.start, footer_start):
                h.kind = "ORG_PHONE"
            hits.append(h)
    for name, pat in rrn_patterns(fix):
        for m in re.finditer(pat, text):
            hits.append(Hit(m.start(), m.end(), "RRN", name))
    pats = PHONE_PATTERNS + (PHONE_FIX_EXTRA if fix else [])
    for name, pat in pats:
        for m in re.finditer(pat, text):
            kind = "ORG_PHONE" if name == "REP" or is_org_context(text, m.start(), footer_start) else "PHONE"
            hits.append(Hit(m.start(), m.end(), kind, name))
    for h in korean_digit_hits(text, fix):
        hits.append(h)
    for m in re.finditer(ADDR_FULL, text):
        s, e = m.start(), m.end()
        s2, e2 = _line_bounds(text, s)
        kind = "ORG_ADDR" if re.search(r"우\s*\d{5}", text[s2:e2]) else "ADDR"
        hits.append(Hit(s, _rstrip(text, s, e), kind, "ADDR_FULL"))
    for m in re.finditer(ADDR_NOSIDO, text):
        s, e = m.start(), m.end()
        before = text[max(0, s - 15):s]
        ok = any(w in before for w in ADDR_CONTEXT_WORDS)
        if fix and not ok:
            after = text[e:e + 12]
            ok = any(w in after for w in ADDR_CONTEXT_AFTER)
        if ok:
            hits.append(Hit(s, _rstrip(text, s, e), "ADDR", "ADDR_NOSIDO"))
    return hits


def _rstrip(text: str, s: int, e: int) -> int:
    while e > s and text[e - 1] in " ,\t":
        e -= 1
    return e


def find_in_value(value: str, kind: str, fix: bool) -> list[tuple[int, int]]:
    """라벨 칸 값 안에서 주민번호·전화번호 위치를 찾는다(구분자 없어도 잡음)."""
    out = []
    if kind == "RRN":
        for _, pat in rrn_patterns(fix):
            out += [(m.start(), m.end()) for m in re.finditer(pat, value)]
    elif kind in ("PHONE", "ORG_PHONE"):
        for _, pat in PHONE_PATTERNS + (PHONE_FIX_EXTRA if fix else []) + [("NOSEP", PHONE_NOSEP)]:
            out += [(m.start(), m.end()) for m in re.finditer(pat, value)]
        out += [(h.start, h.end) for h in korean_digit_hits(value)]
    return out
