"""지시서 7절 정규식 시험과 OCR 전용 규칙 시험. 모든 값은 가짜이다.

.venv/bin/python -m pytest -q tests/test_rules.py
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rules  # noqa: E402


def kinds(text, fix=True, footer=None):
    return sorted({h.kind for h in rules.find_all(text, fix, footer)})


def covered(text, sub, fix=True, kind=None):
    s = text.index(sub)
    e = s + len(sub)
    return any(h.start <= s and e <= h.end and (kind is None or h.kind == kind)
               for h in rules.find_all(text, fix))


# ---------------------------------------------------------------- 주민등록번호
@pytest.mark.parametrize("v", [
    "900101-1234567", "900101 - 1234567", "9001011234567", "900101-1******",
    "900101-*******", "******-1234567", "450315–2******", "900101ㅡ1234567",
])
def test_rrn_hit(v):
    assert covered(f"주민번호 {v} 입니다", v, kind="RRN")


@pytest.mark.parametrize("v", [
    "901301-1234567",   # 13월
    "900132-1234567",   # 32일
    "900101-9234567",   # 뒷자리 첫 숫자 9
    "1900101-1234567",  # 앞에 숫자가 더 붙음
    "123-45-67890",     # 사업자등록번호
])
def test_rrn_miss(v):
    assert "RRN" not in kinds(f"번호 {v} 입니다")


def test_rrn_kordoc_escaped_star():
    # kordoc 마크다운은 *를 \*로 바꿔 내보낸다. 지시서 정규식은 놓치고, 고친 정규식은 잡는다.
    v = r"900101-1\*\*\*\*\*\*"
    t = f"| 주민등록번호 | {v} |"
    assert "RRN" in kinds(t, fix=True)
    assert "RRN" not in kinds(t, fix=False)


# ---------------------------------------------------------------- 전화번호
@pytest.mark.parametrize("v", [
    "010-1234-5678", "010 1234 5678", "01012345678", "010.1234.5678", "011-123-4567",
    "02-123-4567", "(02) 123-4567", "(02)123-4567", "031-123-4567", "064-123-4567",
    "070-1234-5678", "0505-123-4567", "+82-10-1234-5678", "010-****-5678",
])
def test_phone_hit(v):
    t = f"연락처 {v} 입니다"
    assert any(k in kinds(t) for k in ("PHONE", "ORG_PHONE")), v


@pytest.mark.parametrize("v", [
    "2026-10-26",        # 날짜
    "123-45-67890",      # 사업자등록번호
    "제2026-1234호",      # 문서번호
    "05-123-4567",       # 없는 지역번호
    "1234-5678",         # 번호 일부
])
def test_phone_miss(v):
    t = f"참고 {v} 입니다"
    assert not any(k in kinds(t) for k in ("PHONE", "ORG_PHONE")), v


def test_rep_number_is_org():
    assert kinds("대표전화 1588-0000") == ["ORG_PHONE"]


def test_org_phone_by_line():
    t = "주무관 가상인 전화 02-111-2222 전송 02-111-3333"
    assert {h.kind for h in rules.find_all(t, True)} == {"ORG_PHONE"}


@pytest.mark.parametrize("v", ["공일공 이이삼삼 사사오오", "010-이이삼삼-4455", "공일공-1234-오육칠팔"])
def test_korean_digits_hit(v):
    assert covered(f"전화 {v} 로", v, kind="PHONE")


@pytest.mark.parametrize("v", ["일이삼", "이사 오일", "구일 일이"])
def test_korean_digits_miss(v):
    assert "PHONE" not in kinds(f"내용 {v} 이다")


# ---------------------------------------------------------------- 주소
@pytest.mark.parametrize("v", [
    "서울특별시 가상구 샘플로 12",
    "서울특별시 가상구 샘플로12길 34",
    "경기도 가온시 나래구 예시동 123-4",
    "부산광역시 가상구 시험동 산 12",
    "서울특별시 가상구 샘플로 12, 101동 202호",
    "서울특별시가상구샘플로12",   # OCR이 띄어쓰기를 지운 경우
])
def test_addr_full_hit(v):
    assert covered(f"주소 {v} 에서", v, kind="ADDR")


def test_addr_nosido_needs_context():
    v = "가상구 샘플로 12"
    assert covered(f"주소: {v}", v, kind="ADDR")
    assert "ADDR" not in kinds(f"회의는 {v}")


def test_addr_nosido_context_after_fix():
    t = "가상구 샘플로 12 고시원에서 지냈다"
    assert "ADDR" in kinds(t, fix=True)
    assert "ADDR" not in kinds(t, fix=False)


def test_org_addr_with_postcode():
    t = "(우 01234) 서울특별시 가상구 구청로 1"
    assert kinds(t) == ["ORG_ADDR"]


@pytest.mark.parametrize("t", [
    "가상구청 복지정책과",     # 기관명
    "서울특별시장",            # 직함
    "2026. 10. 26.",          # 날짜
])
def test_addr_miss(t):
    assert "ADDR" not in kinds(t)


# ---------------------------------------------------------------- OCR 전용 규칙(스캔·팩스, fixed에서만)
def ocr_kinds(text):
    return sorted({h.kind for h in rules.find_all(text, True, None, True)})


@pytest.mark.parametrize("t,sub", [
    ("주민번호 450315-2**** 입니다", "450315-2****"),       # 별표 일부가 빠짐
    ("| 1948.3.2. | 4803021 |", "4803021"),                # 별표가 통째로 빠짐
    ("연락처 8032-7654321", "8032-7654321"),               # ☎를 8로 읽음
    ("연락 공일공 일이삼사 오육철필", "공일공 일이삼사 오육철필"),  # 한글 숫자 오독
    ("연락:010-01이4455", "010-01이4455"),                 # 숫자·한글 숫자 섞임
    ("해82107788", "82107788"),                            # 국제번호 잔해
    ("서율특별시 가상구 샘플로 12", "서율특별시 가상구 샘플로 12"),  # 시·도 표기 깨짐
])
def test_ocr_hit(t, sub):
    s = t.index(sub)
    e = s + len(sub)
    assert any(h.start <= s and e <= h.end for h in rules.find_all(t, True, None, True)), t


@pytest.mark.parametrize("t", [
    "2026-10-26", "123-45-67890", "복지정책과-12345(2026-10-20)", "1,234,567원",
    "2026.10.18.오 2시", "관련:국지성책과-12345/2026-10-22)",
])
def test_ocr_miss(t):
    assert not any(k in ocr_kinds(t) for k in ("PHONE", "RRN")), t
