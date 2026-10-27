"""가짜화: 진짜 값을 같은 모양의 가짜 값으로 바꾼다.

정규식 수정안을 쓰는 쪽(Claude Code)과 회귀 시험 세트에는 이 결과만 넘긴다.
- 글자 수와 위치를 그대로 둔다(한 글자를 한 글자로 바꾼다). 그래서 표 구조·구분자·라벨 낱말·위치가 남는다.
- 남기는 것: 구분자(공백, -, *, 괄호 등), 라벨 낱말, 시·도 이름, 주소 접미사(시·군·구·동·로·길, -ro·-gil),
  전화 앞자리(010, 02 등), 글자 모양(숫자/한글 숫자/오독 글자/라틴 글자/한자).
- 바꾸는 것: 이름 음절(성씨는 성씨로), 라틴 글자(대소문자 유지), 한자, 숫자(자리마다 다른 숫자),
  한글 숫자(다른 숫자의 한글 숫자), 오독 글자(새 숫자에 맞춘 비슷한 오독 글자), 주소 지명 음절.
check()가 결과에 원래 값이 남았는지 따로 검사한다. 검사에 실패하면 다른 씨앗값으로 다시 만들고,
그래도 실패하면 결과를 쓰지 않는다. 검사 결과 메시지에는 진짜 값을 넣지 않는다.
"""
from __future__ import annotations

import random
import re

import labels
import rules

# ---------------------------------------------------------------- 글자 분류
KDIGIT = dict(rules.KDIGIT)
DIGIT_KO = {"0": "공", "1": "일", "2": "이", "3": "삼", "4": "사", "5": "오", "6": "육", "7": "칠", "8": "팔", "9": "구"}
LATIN_CONF = {"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "i": "1", "Z": "2", "S": "5", "s": "5",
              "b": "6", "G": "6", "B": "8", "g": "9", "q": "9"}
LATIN_GLYPH = {"0": "O", "1": "l", "2": "Z", "5": "S", "6": "b", "8": "B", "9": "g"}
# 한글 숫자를 OCR이 비슷한 글자로 읽은 예(가짜 값의 오독 글자를 만들 때만 쓴다)
KO_CONF = {"0": ["곰", "콩", "궁"], "1": ["밀", "입", "알"], "2": ["미", "리", "어"], "3": ["상", "섬", "산"],
           "4": ["시", "자", "샤"], "5": ["요", "모", "우"], "6": ["욱", "윽", "율"], "7": ["철", "질", "실"],
           "8": ["말", "발", "탈"], "9": ["무", "고", "국"]}

CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"
CHO_SIM = [set("ㄱㄲㅋ"), set("ㄷㄸㅌㄹ"), set("ㅂㅃㅍㅁ"), set("ㅅㅆㅈㅉㅊ"), set("ㅇㅎ"), set("ㄴㄹ")]
JUNG_SIM = [set("ㅏㅑㅓㅕ"), set("ㅗㅛㅜㅠ"), set("ㅡㅣ"), set("ㅐㅔㅒㅖ"), set("ㅘㅝㅙㅞ")]
JONG_SIM = [set("ㄱㄲㅋ"), set("ㄴㅁㅇ"), set("ㄹㄷ"), set(" ㅇ")]


def is_hangul(c: str) -> bool:
    return "가" <= c <= "힣"


def is_hanja(c: str) -> bool:
    return "一" <= c <= "鿿"


def jamo(c: str):
    i = ord(c) - 0xAC00
    return CHO[i // 588], JUNG[(i % 588) // 28], JONG[i % 28]


def _d(a, b, groups):
    if a == b:
        return 0.0
    return 0.5 if any(a in g and b in g for g in groups) else 1.0


def jamo_dist(a: str, b: str) -> float:
    ja, jb = jamo(a), jamo(b)
    return _d(ja[0], jb[0], CHO_SIM) + _d(ja[1], jb[1], JUNG_SIM) + _d(ja[2], jb[2], JONG_SIM)


def closest_kdigit(c: str) -> tuple[str, float]:
    """한글 글자와 자모가 가장 비슷한 한글 숫자(글자, 거리)."""
    best = min(KDIGIT, key=lambda k: (jamo_dist(c, k), k not in DIGIT_KO.values()))
    return best, jamo_dist(c, best)


def digit_of(c: str, confusions: dict | None = None) -> str | None:
    """숫자로 읽을 수 있으면 그 숫자. 오독 글자도 숫자로 본다."""
    if c.isdigit() and c.isascii():
        return c
    if c in KDIGIT:
        return KDIGIT[c]
    if confusions and c in confusions:
        return confusions[c]
    if c in LATIN_CONF:
        return LATIN_CONF[c]
    if is_hangul(c):
        k, dist = closest_kdigit(c)
        if dist <= 1.0:
            return KDIGIT[k]
    return None


def glyph_class(c: str) -> str:
    if c.isdigit() and c.isascii():
        return "digit"
    if c in KDIGIT:
        return "kdigit"
    if c in LATIN_CONF:
        return "latin_conf"
    if is_hangul(c):
        return "ko_conf"
    return "other"


def render(d: str, cls: str, avoid: str, rng: random.Random) -> str | None:
    if cls == "digit":
        return d
    if cls == "kdigit":
        return DIGIT_KO[d]
    if cls == "latin_conf":
        return LATIN_GLYPH.get(d)
    if cls == "ko_conf":
        opts = [x for x in KO_CONF[d] if x != avoid]
        return rng.choice(opts) if opts else None
    return None


# ---------------------------------------------------------------- 남겨 두는 낱말
EN_KEEP = {"seoul", "busan", "daegu", "incheon", "gwangju", "daejeon", "ulsan", "sejong", "gyeonggi", "gangwon",
           "chungcheongbuk", "chungcheongnam", "jeollabuk", "jeollanam", "gyeongsangbuk", "gyeongsangnam", "jeju",
           "do", "si", "gu", "gun", "dong", "eup", "myeon", "ri", "ro", "gil", "daero", "beon", "korea", "republic",
           "of", "the", "fax", "tel", "hp", "no", "apt", "unit", "room", "fl", "floor", "ho", "b", "f", "md", "pdf"}
ADDR_SUFFIX = ["특별자치시", "특별자치도", "특별시", "광역시", "번길", "대로", "아파트", "빌라", "번지",
               "시", "군", "구", "읍", "면", "동", "리", "로", "길", "가", "호", "층"]
SIDO_RX = re.compile(r"^" + rules.SIDO + r"$")
PHONE_PREFIX_RX = re.compile(r"^(?:01[016789]|02|0(?:3[1-3]|4[1-4]|5[1-5]|6[1-4])|070|050)")


def keep_words() -> set[str]:
    """가짜화하지 않는 한글 낱말: 라벨, 직함, 규칙이 문맥으로 쓰는 낱말, 공문에 흔한 낱말."""
    import yaml
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    out = set(labels.TITLE_WORDS) | set(labels.NOT_NAME) | set(rules.ADDR_CONTEXT_WORDS) | set(rules.ADDR_CONTEXT_AFTER)
    cfg = yaml.safe_load((root / "config/labels.yaml").read_text(encoding="utf-8"))

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            out.add(re.sub(r"\s+", "", v))
    walk(cfg)
    sw = root / "config/ner_stopwords.txt"
    if sw.exists():
        out |= {w.strip() for w in sw.read_text(encoding="utf-8").splitlines() if w.strip() and not w.startswith("#")}
    out |= set(COMMON_WORDS)
    out |= EXTRA_KEEP
    return out


# 오답 노트가 더한 칸 이름·예외 낱말(learn.py가 채운다). 이름이 아닌 낱말이라 가짜화하지 않고 남긴다.
EXTRA_KEEP: set[str] = set()


# 공문에 흔히 나오는 낱말(성씨 글자로 시작해 이름처럼 보이지만 이름이 아님). 모르는 낱말은 안전하게 바꾼다.
COMMON_WORDS = """
사망 사망일 사망일시 사망장소 사망원인 사건 사건번호 사항 사실 사유 사회복지 사회복지사 사무소 사용 사람
신고 신고자 신고인 신원 신청 신청인 신분 시신 시설 시청 시간 시행 시스템 조치 조회 조사 정보 정리 정부
이상 이웃 이번 이후 이전 이하 이름 이송 이유 장례 장례식 장례식장 장소 장애 장남 장녀 전화 전송 전결
주소 주민 주민등록 주민센터 주무관 주의 주관 고인 고려 고용 고용주 고시원 공문 공영장례 공고 공유 공지
안치 안내 안전 연락 연락처 연고 연고자 유족 유류품 유가족 유선 한부 한국 한편 기간 기관 기록 기안 기타
도착 도움 문의 문서 민원 발견 발견자 발생 방문 변사 변사자 보호 보호자 보건 보고 부탁 부서 성명 성별
수신 수사 수급 수급자 시행일 오전 오후 요청 원장 원룸 위탁 의뢰 의료 인계 인수 인수자 입원 입소 입소자
처리 첨부 체류 체류지 최초 추가 통보 통지 협조 확인 환자 환자명 회신 국적 외국인 등록 담당 대표 대상
대상자 상황 상기 상주 동거 동생 차녀 차남 장녀 옆집 거주 거주지 가족 가구 친족 배우자 경찰 경찰서
병원 병록번호 생년월일 요양원 재단 나눔 구청 구청장 동장 과장 팀장 국장 소장 원장 책임자 비상연락처
긴급연락처 고용주 사업장 근무 근무지 영문 한글 표기 별지 붙임 끝 위 아래 및 등 또는 각 귀하 귀 기관
""".split()


# ---------------------------------------------------------------- 가짜화
SURNAME_POOL = list("김이박최정강조윤장임한오서신권황안송전홍유고문양손배백허남심노하곽성차주우구민류나진지엄채원천방공현함변염여추도소석선설마길연위표명기반라왕금옥육인맹제모탁국어은편용예경봉")
GIVEN_POOL = list("가나다라마바사아자차카타파하경계고공관광교구국군규근금기길남내녀년노누늘다단달담당대덕도동두득들라락란람랑래량려련렬령례로록론뢰료룡루류륜률르름릉리린림립마만말망매맥면명모목묘무문물미민밀박반발방배백범법벽변별병보복본봉부분불비빈빛사산살삼상새색생서석선설섭성세소속손솔송수숙순술숭슬승시식신실심아악안알암압앙애야약양어억언엄업여역연열염엽영예오옥온올옹완왕외요욕용우욱운울웅원월위유육윤율은을음읍응의이익인일임입잉자작잔장재쟁저적전절점정제조족존졸종좌주죽준중즉증지직진질집징차착찬찰참창채책처척천철첨청체초촌총최추축춘출충취측층치칙친칠침칭쾌타탁탄탈탐탑탕태택토통퇴투특파판팔패팽편평폐포표품풍피필하학한할함합항해핵행향허헌험혁현혈협형혜호혹혼홀홍화확환활황회획횡효후훈훤휘휴흉흑흔흘흠흡흥희흰히힘")
HANJA_POOL = list("金李朴崔鄭姜趙尹張林韓吳徐申權黃安宋全洪柳高文梁孫裵白許南沈盧河郭成車朱禹具閔明光春秋東西泉石松竹梅蘭菊玉珠雲雨雪風山川江海")


class Faker:
    def __init__(self, seed: int, forbid_syllables: set[str], forbid_hanja: set[str]):
        self.rng = random.Random(seed)
        self.syl: dict[str, str] = {}
        self.place: dict[str, str] = {}
        self.han: dict[str, str] = {}
        self.forbid = set(forbid_syllables) | set(KDIGIT) | {v for vs in KO_CONF.values() for v in vs}
        self.forbid_h = set(forbid_hanja)
        letters = "abcdefghijklmnopqrstuvwxyz"
        while True:
            p = list(letters)
            self.rng.shuffle(p)
            if all(a != b for a, b in zip(letters, p)):
                break
        self.lat = dict(zip(letters, p))

    def _pick(self, pool, used_map, orig):
        cand = [x for x in pool if x not in self.forbid and x != orig and x not in used_map.values()]
        if not cand:
            cand = [x for x in pool if x not in self.forbid and x != orig]
        return self.rng.choice(cand)

    def name_syl(self, c: str, surname: bool) -> str:
        if c not in self.syl:
            self.syl[c] = self._pick(SURNAME_POOL if surname else GIVEN_POOL, self.syl, c)
        return self.syl[c]

    def place_syl(self, c: str) -> str:
        if c not in self.place:
            self.place[c] = self._pick(GIVEN_POOL, self.place, c)
        return self.place[c]

    def hanja(self, c: str) -> str:
        if c not in self.han:
            cand = [x for x in HANJA_POOL if x != c and x not in self.forbid_h and x not in self.han.values()]
            self.han[c] = self.rng.choice(cand or [x for x in HANJA_POOL if x != c])
        return self.han[c]

    def latin(self, c: str) -> str:
        lo = c.lower()
        if lo not in self.lat:
            return c
        r = self.lat[lo]
        return r.upper() if c.isupper() else r

    def other_digit(self, d: str, allowed: str = "0123456789") -> str:
        cand = [x for x in allowed if x != d]
        return self.rng.choice(cand) if cand else d     # 고를 수 없으면 그대로 두고 검사에서 걸리게 한다


def _name_chars(s: str, fk: Faker) -> str:
    out = []
    first = True
    i = 0
    while i < len(s):
        c = s[i]
        if is_hangul(c):
            two = s[i:i + 2]
            surname = first and (two in labels.TWO_CHAR_SURNAMES or c in labels.SURNAMES)
            out.append(fk.name_syl(c, surname))
            first = False
        elif is_hanja(c):
            out.append(fk.hanja(c))
        elif c.isascii() and c.isalpha():
            out.append(fk.latin(c))
        elif c.isdigit():
            out.append(fk.other_digit(c))
        else:
            out.append(c)
            if c.isspace() or c in "(),·/":
                first = True
        i += 1
    return "".join(out)


def _number_chars(s: str, kind: str, fk: Faker, confusions=None) -> tuple[str, list[int]]:
    """주민번호·전화번호를 자리마다 다른 숫자로 바꾼다. 남긴 자리(앞자리)의 위치 목록도 돌려준다."""
    pos = [i for i, c in enumerate(s) if digit_of(c, confusions) is not None and not (c.isspace())]
    digits = [digit_of(s[i], confusions) for i in pos]
    out = list(s)
    kept = []
    new = [None] * len(pos)
    start = 0
    if kind in ("PHONE", "ORG_PHONE"):
        m = PHONE_PREFIX_RX.match("".join(digits))
        if m:
            start = len(m.group(0))
            for j in range(start):
                new[j] = digits[j]
                kept.append(pos[j])
    if kind == "RRN" and len(digits) >= 6:
        # 앞 6자리: 자리마다 다른 유효 날짜
        for _ in range(500):
            cand = [fk.other_digit(d) for d in digits[:6]]
            cand[2] = "1" if digits[2] == "0" else "0"
            if cand[2] == "1":
                cand[3] = fk.other_digit(digits[3], "012")
            else:
                cand[3] = fk.other_digit(digits[3], "123456789")
            cand[4] = fk.other_digit(digits[4], "012")
            cand[5] = fk.other_digit(digits[5], "123456789" if cand[4] == "0" else "012345678")
            ok = True
            for j in range(6):
                need = glyph_class(s[pos[j]])
                if need == "latin_conf" and cand[j] not in LATIN_GLYPH:
                    ok = False
            if ok:
                break
        new[:6] = cand
        start = 6
        if len(digits) >= 7:
            g = digits[6]
            cls = "1234" if g in "1234" else "5678"
            allowed = cls
            if glyph_class(s[pos[6]]) == "latin_conf":
                allowed = "".join(x for x in cls if x in LATIN_GLYPH)
            new[6] = fk.other_digit(g, allowed)
            start = 7
    for j in range(start, len(pos)):
        if new[j] is not None:
            continue
        cls = glyph_class(s[pos[j]])
        allowed = "".join(x for x in "0123456789" if x in LATIN_GLYPH) if cls == "latin_conf" else "0123456789"
        new[j] = fk.other_digit(digits[j], allowed)
    for j, i in enumerate(pos):
        if i in kept:
            continue
        cls = glyph_class(s[i])
        g = render(new[j], cls, s[i], fk.rng)
        out[i] = g if g else s[i]
    return "".join(out), kept


def _addr_chars(s: str, fk: Faker) -> tuple[str, list[int]]:
    out = list(s)
    kept = []
    for m in re.finditer(r"[가-힣]+|[A-Za-z]+|\d+|[一-鿿]+", s):
        tok, a = m.group(0), m.start()
        if is_hangul(tok[0]):
            if SIDO_RX.match(tok):
                kept.extend(range(a, a + len(tok)))
                continue
            suf = next((x for x in ADDR_SUFFIX if tok.endswith(x) and len(tok) > len(x)), "")
            if not suf and tok in ADDR_SUFFIX:
                suf = tok
            body = len(tok) - len(suf)
            for k in range(body):
                out[a + k] = fk.place_syl(tok[k])
            kept.extend(range(a + body, a + len(tok)))
        elif tok.isascii() and tok.isalpha():
            if tok.lower() in EN_KEEP:
                kept.extend(range(a, a + len(tok)))
                continue
            for k, c in enumerate(tok):
                out[a + k] = fk.latin(c)
        elif tok.isdigit():
            for k, c in enumerate(tok):
                out[a + k] = fk.other_digit(c)
        else:
            for k, c in enumerate(tok):
                out[a + k] = fk.hanja(c)
    return "".join(out), kept


def conservative_spans(text: str, known: list[tuple[int, int]], keep: set[str]) -> list[tuple[int, int, str]]:
    """표시나 가림이 없어도 바꿔 두는 곳: 이름처럼 보이는 낱말, 씨·님 앞 낱말, 라틴 낱말, 한자, 4자리 이상 숫자."""
    def covered(s, e):
        return any(a <= s and e <= b for a, b in known)
    out = []
    for m in re.finditer(r"[가-힣]+", text):
        tok = m.group(0)
        base = labels._strip_josa(tok) or tok
        if base in keep or tok in keep or re.sub(r"(은|는|이|가|을|를|의|에|에서|에게|께|과|와|로|으로|도|만)$", "", tok) in keep:
            continue
        if all(c in KDIGIT for c in base):
            continue
        s, e = m.start(), m.start() + len(base)
        if covered(s, e):
            continue
        if labels._is_name_token(base) and len(base) <= 5:
            out.append((s, e, "NAME"))
        elif re.match(r"\s?[씨님]", text[m.end():m.end() + 2]) and 2 <= len(tok) <= 4:
            out.append((m.start(), m.end(), "NAME"))
    # HTML 표 태그(<tr><td colspan="3">)와 그림 파일 이름은 문서 구조이므로 남긴다
    tags = [(m.start(), m.end()) for m in re.finditer(r"</?[A-Za-z][^<>\n]*>|\]\([^)\n]*\)", text)]
    for m in re.finditer(r"[A-Za-z]{2,}", text):
        if m.group(0).lower() in EN_KEEP or covered(m.start(), m.end()):
            continue
        if any(a <= m.start() and m.end() <= b for a, b in tags):
            continue
        out.append((m.start(), m.end(), "LATIN"))
    for m in re.finditer(r"[一-鿿]+", text):
        if m.group(0) == "故" or covered(m.start(), m.end()):
            continue
        out.append((m.start(), m.end(), "NAME"))
    # 구분자로 이어진 숫자 묶음(123-45-67890, 2026. 10. 26.)도 숫자가 4개 이상이면 통째로 바꾼다
    for m in re.finditer(r"\d(?:[\d\-–.,]|\s(?=\d))*\d", text):
        if sum(c.isdigit() for c in m.group(0)) >= 4 and not covered(m.start(), m.end()):
            out.append((m.start(), m.end(), "DIGITS"))
    return out


def fakeify(text: str, spans: list[tuple[int, int, str]], seed: int = 1, confusions: dict | None = None,
            conservative: bool = True):
    """spans: (시작, 끝, 종류) 진짜 값 구간. 결과: (가짜 글, 바꾼 구간 목록[(s,e,kind,kept_positions)])."""
    keep = keep_words()
    forbid = set()
    forbid_h = set()
    for s, e, k in spans:
        for c in text[s:e]:
            if is_hangul(c):
                forbid.add(c)
            elif is_hanja(c):
                forbid_h.add(c)
    allspans = [(s, e, k) for s, e, k in spans if e > s]
    if conservative:
        allspans += conservative_spans(text, [(s, e) for s, e, _ in allspans], keep)
        for s, e, k in allspans:
            for c in text[s:e]:
                if is_hangul(c) and k == "NAME":
                    forbid.add(c)
    fk = Faker(seed, forbid, forbid_h)
    out = list(text)
    done = []
    # 겹치는 구간은 앞에서부터 한 번만 바꾼다
    taken = [False] * len(text)
    for s, e, k in sorted(allspans, key=lambda x: (x[0], -(x[1] - x[0]))):
        if any(taken[s:e]):
            # 겹치면 겹치지 않는 부분만 따로 처리
            segs, cur = [], None
            for i in range(s, e):
                if not taken[i]:
                    cur = [i, i + 1] if cur is None else [cur[0], i + 1]
                elif cur:
                    segs.append(tuple(cur))
                    cur = None
            if cur:
                segs.append(tuple(cur))
        else:
            segs = [(s, e)]
        for a, b in segs:
            seg = text[a:b]
            if k in ("RRN", "PHONE", "ORG_PHONE"):
                new, kept = _number_chars(seg, k, fk, confusions)
            elif k in ("ADDR", "ORG_ADDR"):
                new, kept = _addr_chars(seg, fk)
            elif k == "DIGITS":
                new, kept = "".join(fk.other_digit(c) if c.isdigit() else c for c in seg), []
            else:
                new, kept = _name_chars(seg, fk), []
            out[a:b] = list(new)
            for i in range(a, b):
                taken[i] = True
            done.append((a, b, k, [a + x for x in kept]))
    return "".join(out), done


# ---------------------------------------------------------------- 검사
STRUCT = re.compile(r"[^0-9A-Za-z가-힣一-鿿]")


def _norm_digits(s: str, confusions=None) -> str:
    out = []
    for c in s:
        d = digit_of(c, confusions) if (c.isdigit() or c in KDIGIT or c in LATIN_CONF or (confusions and c in confusions)) else None
        out.append(d if d else " ")
    return "".join(out)


def _digit_runs(s: str, confusions=None) -> str:
    """숫자로 읽히는 글자를 이어 붙이되, 구분자(공백·-·.·괄호·*·\\)는 건너뛰고 그 밖의 글자에서는 끊는다.
    문서 전체 숫자를 한 줄로 이으면 서로 다른 번호가 맞붙어 우연히 4자리가 겹치므로 끊어 둔다."""
    out = []
    for c in s:
        if c.isdigit() or c in KDIGIT or c in LATIN_CONF or (confusions and c in confusions):
            d = digit_of(c, confusions)
            out.append(d if d else "|")
        elif c.isspace() or c in "-–—.()*\\":
            continue
        else:
            out.append("|")
    return "".join(out)


def check(orig: str, fake: str, done: list, values: list[tuple[str, str]], confusions=None) -> list[str]:
    """가짜화 결과 검사. values: (종류, 진짜 값) 목록. 문제 설명 목록을 돌려준다(진짜 값은 넣지 않는다)."""
    probs = []
    if len(orig) != len(fake):
        return ["글자 수가 달라졌다"]
    # 1) 바꾼 구간: 구조 글자와 허용한 자리(시·도, 주소 접미사, 전화 앞자리)를 빼고는 자리마다 달라야 한다
    for a, b, k, kept in done:
        allow = set(kept)
        # 허용한 자리가 정말 허용 대상인지 따로 확인한다
        if k in ("PHONE", "ORG_PHONE") and kept:
            pre = "".join(digit_of(orig[i], confusions) or "" for i in kept)
            if not PHONE_PREFIX_RX.fullmatch(pre):
                probs.append(f"{k} 구간에서 앞자리가 아닌 숫자를 남겼다")
        if k in ("ADDR", "ORG_ADDR"):
            for m in re.finditer(r"[가-힣]+|[A-Za-z]+", orig[a:b]):
                tok, s0 = m.group(0), a + m.start()
                kept_idx = [i for i in range(s0, s0 + len(tok)) if i in allow]
                if not kept_idx:
                    continue
                kept_txt = "".join(orig[i] for i in kept_idx)
                if not (SIDO_RX.match(tok) or kept_txt in ADDR_SUFFIX or tok.lower() in EN_KEEP):
                    probs.append("주소 구간에서 시·도 이름·접미사가 아닌 글자를 남겼다")
        for i in range(a, b):
            if i in allow or STRUCT.match(orig[i]):
                continue
            if orig[i] == fake[i]:
                probs.append(f"{k} 구간의 {i - a + 1}번째 글자가 그대로다")
    # 2) 원래 값이 통째로 남았는지(띄어쓰기 무시)
    fake_ns = re.sub(r"\s+", "", fake)
    fake_dg = _digit_runs(fake, confusions)
    for kind, v in values:
        vn = re.sub(r"\s+", "", v)
        if kind == "NAME":
            hs = "".join(c for c in vn if is_hangul(c) or is_hanja(c))
            if len(hs) >= 2 and hs in fake_ns:
                probs.append("원래 이름이 그대로 남았다")
            for w in re.findall(r"[A-Za-z]{3,}", v):
                if w.lower() not in EN_KEEP and re.search(re.escape(w), fake, re.I):
                    probs.append("원래 라틴 이름 낱말이 남았다")
        elif kind in ("RRN", "PHONE", "ORG_PHONE"):
            d = re.sub(r"\s+", "", _norm_digits(v, confusions))
            m = PHONE_PREFIX_RX.match(d) if kind != "RRN" else None
            body = d[len(m.group(0)):] if m else d
            for j in range(len(body) - 3):
                if body[j:j + 4] in fake_dg:
                    probs.append(f"{kind} 원래 숫자 4자리가 남았다")
                    break
        elif kind in ("ADDR", "ORG_ADDR"):
            for tok in re.findall(r"[가-힣]{2,}", v):
                suf = next((x for x in ADDR_SUFFIX if tok.endswith(x) and len(tok) > len(x)), "")
                core = tok[:len(tok) - len(suf)] if suf else tok
                if SIDO_RX.match(tok) or len(core) < 2:
                    continue
                if core in fake_ns:
                    probs.append("원래 지명 낱말이 남았다")
            for w in re.findall(r"[A-Za-z]{3,}", v):
                if w.lower() not in EN_KEEP and re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", fake, re.I):
                    probs.append("원래 라틴 지명 낱말이 남았다")
            dg = re.findall(r"\d{3,}", v)
            for x in dg:
                if re.search(r"(?<!\d)" + x + r"(?!\d)", fake):
                    probs.append("원래 주소 번호가 남았다")
    # 3) 이름 음절: 바꾼 이름 구간에 원래 이름 음절이 들어가지 않았는지
    name_syl = {c for kind, v in values if kind == "NAME" for c in v if is_hangul(c)}
    for a, b, k, kept in done:
        if k == "NAME":
            if any(c in name_syl for c in fake[a:b]):
                probs.append("바꾼 이름에 원래 이름 음절이 들어갔다")
    return sorted(set(probs))


def fakeify_checked(text, spans, values, confusions=None, seeds=range(1, 30)):
    """검사를 통과할 때까지 씨앗값을 바꿔 가며 만든다. 끝내 실패하면 (None, None, 문제 목록)."""
    last = []
    for sd in seeds:
        fake, done = fakeify(text, spans, sd, confusions)
        probs = check(text, fake, done, values, confusions)
        if not probs:
            return fake, done, []
        last = probs
    return None, None, last
