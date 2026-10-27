"""가짜 부고 공문 견본과 정답표를 만든다.

모든 이름·번호·주소는 지어낸 값이다. 실제 사람 정보는 쓰지 않는다.
결과:
  tests/fake/src/<ID>.md            정답 원문(사람이 읽는 형태)
  tests/fake/<ID>_text.pdf          글자가 든 PDF
  tests/fake/<ID>_hwpx.hwpx         HWPX (일부 견본만, kordoc generate 사용)
  tests/fake/<ID>_scan.pdf          스캔본 흉내(300dpi 회색조 이미지만 든 PDF)
  tests/fake/<ID>_fax.png           팩스 흉내(200dpi, 1비트 흑백, 기울기·잡음)
  tests/fake/answers/<ID>.answer.json  가려야 할 값과 가리면 안 되는 값
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

import fitz  # pymupdf
import numpy as np
from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fake"
# 견본 PDF에 쓸 한글 글꼴. FAKE_FONT 환경 변수가 없으면 아래 후보 가운데 있는 것을 쓴다.
_FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/malgun.ttf"),                       # Windows 맑은 고딕
    Path.home() / "Library/Fonts/NotoSansKR[wght].ttf",         # macOS(사용자 설치 Noto Sans KR)
    Path("/Library/Fonts/NotoSansKR[wght].ttf"),
    Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),   # 리눅스 나눔고딕
]
FONT = os.environ.get("FAKE_FONT") or next((str(f) for f in _FONT_CANDIDATES if f.exists()), "")
# kordoc 오프라인 래퍼. NANUM_KORDOC 환경 변수가 없으면 Windows에서는 app/kordoc-safe.cmd를,
# 그 밖의 운영체제에서는 PATH의 kordoc을 쓴다.
KORDOC = Path(os.environ.get("NANUM_KORDOC")
              or (ROOT / "app" / "kordoc-safe.cmd" if os.name == "nt" else shutil.which("kordoc") or "kordoc"))

# 공통으로 넣는 "가리면 안 되는 값"
COMMON_MUST_NOT = ["복지정책과-12345", "2026-10-26", "1,234,567원", "123-45-67890", "이사", "오후", "구청"]

# ---------------------------------------------------------------- 견본 정의
# blocks: ("h", 글) 기관명, ("t", 글) 제목, ("p", 글) 문단, ("table", rows, spans)
# rows의 칸은 문자열. spans는 reportlab SPAN 좌표 목록 [((c0,r0),(c1,r1)), ...]
# answer 항목: type(NAME/RRN/PHONE/ADDR), value(대표값), role, forms(문서에 실제로 나오는 표기),
#   주소는 keys(남아 있으면 누출로 보는 핵심 조각, 공백 무시)

DOCS = []

DOCS.append(dict(
    id="D01", form="A-가상구청 협조요청",
    blocks=[
        ("h", "가 상 구"),
        ("p", "수신  사단법인 나눔과나눔 이사장"),
        ("p", "(경유)"),
        ("t", "제목  무연고 사망자 공영장례 지원 요청"),
        ("p", "1. 귀 기관의 무궁한 발전을 기원합니다."),
        ("p", "2. 관련: 복지정책과-12345(2026-10-20)"),
        ("p", "3. 우리 구 관내에서 발생한 무연고 사망자에 대하여 아래와 같이 공영장례 지원을 요청하오니 협조하여 주시기 바랍니다."),
        ("table", [
            ["성 명", "홍길동", "주민등록번호", "500101-1234567"],
            ["주 소", "서울특별시 가상구 예시로 12, 101동 202호", "", ""],
            ["사망일시", "2026. 10. 18. 오후 2시 30분", "사망장소", "가상구 샘플동 123-4번지"],
            ["연고자", "김철수 (장남)", "연락처", "010-1234-5678"],
            ["신고인", "이영희", "연락처", "(02) 123-4567"],
        ], [((1, 1), (3, 1))]),
        ("p", "4. 고인 홍길동 님은 2026-10-18 자택에서 숨진 채 발견되었으며, 신고인 이영희 씨는 같은 건물에 사는 이웃입니다."),
        ("p", "5. 연고자인 장남 김철수 씨에게 수차례 연락하였으나 시신 인수를 거부하였고, 회신은 공일공 일이삼사 오육칠팔 로 해 달라고 하였습니다."),
        ("p", "6. 생전 이웃들은 고인을 길동 씨라고 불렀으며, 사망진단서에는 성명이 홍 길 동 으로 띄어 적혀 있습니다."),
        ("p", "7. 故 홍길동 님의 장례비 1,234,567원은 장례업체(사업자등록번호 123-45-67890)에 지급할 예정이며, 발인은 2026-10-26 오후 1시입니다."),
        ("p", "8. 고인은 2019년 서울특별시 가상구 예시로 12, 101동 202호로 이사한 뒤 혼자 지냈습니다."),
        ("p", "끝."),
        ("h", "가상구청장"),
        ("p", "주무관 박민수   팀장 정예준   복지정책과장 전결 2026. 10. 26."),
        ("p", "시행 복지정책과-12345 (2026-10-26)  접수"),
        ("p", "우 01234 서울특별시 가상구 가상로 100 가상구청 복지정책과 / 전화 02-2600-1234 / 전송 02-2600-1299 / 대표전화 1588-0000 / 비공개"),
    ],
    answer=[
        dict(type="NAME", value="홍길동", role="사망자", forms=["홍길동", "홍 길 동", "길동"]),
        dict(type="NAME", value="김철수", role="연고자", forms=["김철수"]),
        dict(type="NAME", value="이영희", role="신고인", forms=["이영희"]),
        dict(type="NAME", value="박민수", role="담당공무원", forms=["박민수"]),
        dict(type="NAME", value="정예준", role="담당공무원", forms=["정예준"]),
        dict(type="RRN", value="500101-1234567", role="사망자", forms=["500101-1234567"]),
        dict(type="PHONE", value="010-1234-5678", role="연고자", forms=["010-1234-5678", "공일공 일이삼사 오육칠팔"]),
        dict(type="PHONE", value="(02) 123-4567", role="신고인", forms=["(02) 123-4567"]),
        dict(type="PHONE", value="02-2600-1234", role="기관", forms=["02-2600-1234"]),
        dict(type="PHONE", value="02-2600-1299", role="기관", forms=["02-2600-1299"]),
        dict(type="PHONE", value="1588-0000", role="기관", forms=["1588-0000"]),
        dict(type="ADDR", value="서울특별시 가상구 예시로 12, 101동 202호", role="사망자", keys=["예시로12", "101동202호"]),
        dict(type="ADDR", value="가상구 샘플동 123-4번지", role="사망장소", keys=["샘플동123-4"]),
        dict(type="ADDR", value="서울특별시 가상구 가상로 100", role="기관", keys=["가상로100"]),
    ],
))

DOCS.append(dict(
    id="D02", form="A-부산 가람구 처리요청(라벨 변형)",
    blocks=[
        ("h", "부산광역시 가람구"),
        ("p", "수신  나눔과나눔 (사무국장)"),
        ("t", "제목  무연고사망자 장례 처리 협조 요청"),
        ("p", "1. 관련: 복지정책과-12345(2026-10-21)"),
        ("p", "2. 아래 사망자의 연고자가 시신 인수를 포기하여 공영장례 지원을 요청합니다."),
        ("table", [
            ["사망자 성명", "남궁민호", "성별/나이", "남 / 81세"],
            ["주민등록번호", "450315-2******", "최종주소지", "부산광역시 가람구 해솔로 45-7, 3층"],
            ["유족", "남궁슬기 (조카)", "연락처", "010 9876 5432"],
            ["신고인", "서문옥 (원룸 관리인)", "전화번호", "051-222-3344"],
        ], []),
        ("p", "3. 남궁민호 님은 2026. 10. 19. 오후 4시경 원룸에서 사망한 채 발견되었습니다. 원룸 관리인 서문옥 씨가 처음 발견하였고, 인근 편의점 직원 탁상진 씨의 진술에 따르면 고인은 일주일 전부터 보이지 않았다고 합니다."),
        ("p", "4. 조카 남궁슬기 씨는 장례 참석은 어렵다고 하였으며, 민호 씨의 유품 정리는 구청에서 진행합니다. 남궁 씨 집안의 다른 친족은 확인되지 않았습니다."),
        ("p", "5. 장례비 1,234,567원(장례업체 사업자등록번호 123-45-67890)은 2026-10-26 지급 예정입니다."),
        ("p", "끝."),
        ("h", "부산광역시 가람구청장"),
        ("p", "주무관 윤하늘   사회복지팀장 도경수   2026. 10. 26."),
        ("p", "우 48000 부산광역시 가람구 구청로 1 / 전화 051-600-7000 / 팩스 051-600-7099"),
    ],
    answer=[
        dict(type="NAME", value="남궁민호", role="사망자", forms=["남궁민호", "민호", "남궁"]),
        dict(type="NAME", value="남궁슬기", role="연고자", forms=["남궁슬기"]),
        dict(type="NAME", value="서문옥", role="신고인", forms=["서문옥"]),
        dict(type="NAME", value="탁상진", role="목격자", forms=["탁상진"]),
        dict(type="NAME", value="윤하늘", role="담당공무원", forms=["윤하늘"]),
        dict(type="NAME", value="도경수", role="담당공무원", forms=["도경수"]),
        dict(type="RRN", value="450315-2******", role="사망자", forms=["450315-2******"]),
        dict(type="PHONE", value="010 9876 5432", role="연고자", forms=["010 9876 5432"]),
        dict(type="PHONE", value="051-222-3344", role="신고인", forms=["051-222-3344"]),
        dict(type="PHONE", value="051-600-7000", role="기관", forms=["051-600-7000"]),
        dict(type="PHONE", value="051-600-7099", role="기관", forms=["051-600-7099"]),
        dict(type="ADDR", value="부산광역시 가람구 해솔로 45-7, 3층", role="사망자", keys=["해솔로45-7"]),
        dict(type="ADDR", value="부산광역시 가람구 구청로 1", role="기관", keys=["구청로1"]),
    ],
))

DOCS.append(dict(
    id="D03", form="A-경기 가상시 통보(고인·발견자, 한자 병기)",
    blocks=[
        ("h", "경기도 가상시"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  무연고 사망자 공영장례 대상자 통보"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("p", "2. 무연고 사망자가 발생하여 아래와 같이 통보하오니 공영장례 진행에 협조하여 주시기 바랍니다."),
        ("table", [
            ["고인", "황보은정(皇甫恩貞)", "주민번호", "620505-2987654"],
            ["주소지", "경기도 가상시 샘플동 123-4번지", "", ""],
            ["연고자", "없음", "연락처", "해당없음"],
            ["발견자", "가상경찰서 순경 문태호", "연락처", "031-987-6543"],
        ], [((1, 1), (3, 1))]),
        ("p", "3. 황보 은정 님은 가상시 샘플동 123-4번지 반지하 방에서 숨진 채 발견되었습니다. 은정 씨는 기초생활수급자로 등록되어 있었습니다."),
        ("p", "4. 발견 당시 집주인 염소연 씨가 문이 잠겨 있다며 경찰에 신고하였습니다."),
        ("p", "5. 장례 일시: 2026-10-26 오후 3시, 비용 1,234,567원(사업자등록번호 123-45-67890)."),
        ("p", "끝."),
        ("h", "가상시장"),
        ("p", "담당자 주무관 한소망  전화 031-8000-1234  전송 031-8000-1299"),
    ],
    answer=[
        dict(type="NAME", value="황보은정", role="사망자", forms=["황보은정", "皇甫恩貞", "황보 은정", "은정"]),
        dict(type="NAME", value="문태호", role="신고인", forms=["문태호"]),
        dict(type="NAME", value="염소연", role="신고인", forms=["염소연"]),
        dict(type="NAME", value="한소망", role="담당공무원", forms=["한소망"]),
        dict(type="RRN", value="620505-2987654", role="사망자", forms=["620505-2987654"]),
        dict(type="PHONE", value="031-987-6543", role="신고인", forms=["031-987-6543"]),
        dict(type="PHONE", value="031-8000-1234", role="기관", forms=["031-8000-1234"]),
        dict(type="PHONE", value="031-8000-1299", role="기관", forms=["031-8000-1299"]),
        dict(type="ADDR", value="경기도 가상시 샘플동 123-4번지", role="사망자", keys=["샘플동123-4"]),
    ],
    must_not_extra=["없음", "해당없음"],
))

DOCS.append(dict(
    id="D04", form="B-대구 가온구 주민센터 사망자 통보(가로표, 여러 사람)",
    blocks=[
        ("h", "대구광역시 가온구 은하동 행정복지센터"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  관내 무연고 사망자 발생 통보 및 장례 지원 요청"),
        ("p", "1. 관련: 복지정책과-12345(2026-10-22)"),
        ("p", "2. 관내에서 아래와 같이 사망자가 발생하였으나 연고자가 장례를 치를 수 없어 통보합니다."),
        ("table", [
            ["구분", "성명", "생년월일", "주민등록번호", "주소", "연락처"],
            ["사망자", "강덕수", "1948. 3. 2.", "480302-1******", "대구광역시 가온구 은하로 33", "-"],
            ["연고자(배우자)", "임순례", "1952. 7. 11.", "520711-2345678", "같음", "010-5555-0101"],
            ["신고인", "노금례", "", "", "대구광역시 가온구 은하로 35", "053-123-4567"],
        ], []),
        ("p", "3. 사망자 강덕수(남, 78세)는 2026. 10. 20. 오후 자택에서 숨졌으며, 배우자 임순례 씨는 요양병원 입원 중으로 장례를 치를 수 없다고 하였습니다."),
        ("p", "4. 고인은 2019년 현 주소지로 이사하였으며, 이웃들은 덕수 씨를 조용한 분으로 기억합니다."),
        ("p", "5. 배우자 측 보호자 연락처는 공일공 오오오오 공일공일 입니다. 신고인 노금례 씨는 옆집 주민입니다."),
        ("p", "6. 장례비 1,234,567원 (업체 사업자등록번호 123-45-67890), 지급 예정일 2026-10-26."),
        ("p", "끝."),
        ("h", "은하동장"),
        ("p", "담당 맞춤형복지팀 주무관 구은비  ☎ 053-200-1111"),
    ],
    answer=[
        dict(type="NAME", value="강덕수", role="사망자", forms=["강덕수", "덕수"]),
        dict(type="NAME", value="임순례", role="연고자", forms=["임순례"]),
        dict(type="NAME", value="노금례", role="신고인", forms=["노금례"]),
        dict(type="NAME", value="구은비", role="담당공무원", forms=["구은비"]),
        dict(type="RRN", value="480302-1******", role="사망자", forms=["480302-1******"]),
        dict(type="RRN", value="520711-2345678", role="연고자", forms=["520711-2345678"]),
        dict(type="PHONE", value="010-5555-0101", role="연고자", forms=["010-5555-0101", "공일공 오오오오 공일공일"]),
        dict(type="PHONE", value="053-123-4567", role="신고인", forms=["053-123-4567"]),
        dict(type="PHONE", value="053-200-1111", role="기관", forms=["053-200-1111"]),
        dict(type="ADDR", value="대구광역시 가온구 은하로 33", role="사망자", keys=["은하로33"]),
        dict(type="ADDR", value="대구광역시 가온구 은하로 35", role="신고인", keys=["은하로35"]),
    ],
    must_not_extra=["같음", "1948. 3. 2.", "1952. 7. 11."],
))

DOCS.append(dict(
    id="D05", form="C-인천 가나구 통보(표 밖 라벨 : 값)",
    blocks=[
        ("h", "인천광역시 가나구"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  무연고 사망자 발생 통보"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("p", "2. 무연고 사망자 인적사항"),
        ("p", "   가. 고인 : 故 송미경 (여, 69세)"),
        ("p", "   나. 주민등록번호 : 570920-2123456"),
        ("p", "   다. 주소 : 인천광역시 가나구 바다로 101번길 9, 2층"),
        ("p", "   라. 연고자 : 무연고 (가족관계 확인 결과 연고자 없음)"),
        ("p", "   마. 신고인 : 공동주택 관리소장 유창훈 (☎ 032-765-4321)"),
        ("p", "3. 송미경 님은 생전에 가나구 별빛로 7 고시원에서도 지낸 적이 있으며, 이웃 배정호 씨가 오후 늦게 연락이 닿지 않는다고 알려 왔습니다."),
        ("p", "4. 고인의 휴대전화(010.4321.8765)는 해지된 상태이며, 미경 씨의 유품은 관리사무소에 보관 중입니다."),
        ("p", "5. 장례비 1,234,567원 (사업자등록번호 123-45-67890), 발인 2026-10-26."),
        ("p", "끝."),
        ("h", "가나구청장"),
        ("p", "주무관 서지후  협조자 희망복지팀 주무관 이도윤  전화 032-440-1234"),
    ],
    answer=[
        dict(type="NAME", value="송미경", role="사망자", forms=["송미경", "미경"]),
        dict(type="NAME", value="유창훈", role="신고인", forms=["유창훈"]),
        dict(type="NAME", value="배정호", role="이웃", forms=["배정호"]),
        dict(type="NAME", value="서지후", role="담당공무원", forms=["서지후"]),
        dict(type="NAME", value="이도윤", role="담당공무원", forms=["이도윤"]),
        dict(type="RRN", value="570920-2123456", role="사망자", forms=["570920-2123456"]),
        dict(type="PHONE", value="032-765-4321", role="신고인", forms=["032-765-4321"]),
        dict(type="PHONE", value="010.4321.8765", role="사망자", forms=["010.4321.8765"]),
        dict(type="PHONE", value="032-440-1234", role="기관", forms=["032-440-1234"]),
        dict(type="ADDR", value="인천광역시 가나구 바다로 101번길 9, 2층", role="사망자", keys=["바다로101번길9"]),
        dict(type="ADDR", value="가나구 별빛로 7", role="사망자", keys=["별빛로7"]),
    ],
    must_not_extra=["무연고"],
))

DOCS.append(dict(
    id="D06", form="C-전남 가온군 통보(망인·상주, 혼합 표기)",
    blocks=[
        ("h", "전라남도 가온군"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  무연고사망자 장례 지원 요청"),
        ("p", "1. 관련: 복지정책과-12345(2026-10-23)"),
        ("p", "2. 망인 인적사항"),
        ("p", "   ○ 망인 : 진말자(陳末子), 여, 1940년생"),
        ("p", "   ○ 주민번호 : 400808 - 2765432"),
        ("p", "   ○ 상주 : 진 동 철 (아들)  연락처 : 010-이이삼삼-4455"),
        ("p", "3. 망 진말자 님은 전라남도 가온군 햇살면 들꽃길 12-3 자택에서 2026. 10. 21. 오후 사망하였습니다. 아들 진동철 씨는 경제적 사정으로 장례를 치를 수 없다고 하였습니다."),
        ("p", "4. 마을 이장 권오복 씨(061-555-0909)가 장례 절차를 도울 예정이며, 말자 씨의 친척은 더 확인되지 않았습니다."),
        ("p", "5. 해외 체류 중인 손녀의 연락처 +82 10-7777-8888 로도 안내하였습니다."),
        ("p", "6. 비용 1,234,567원, 사업자등록번호 123-45-67890, 처리일 2026-10-26."),
        ("p", "끝."),
        ("h", "가온군수"),
        ("p", "담당자 : 사회복지주무관 노다은   팩스 061-123-4568"),
    ],
    answer=[
        dict(type="NAME", value="진말자", role="사망자", forms=["진말자", "陳末子", "말자"]),
        dict(type="NAME", value="진동철", role="연고자", forms=["진동철", "진 동 철"]),
        dict(type="NAME", value="권오복", role="이장", forms=["권오복"]),
        dict(type="NAME", value="노다은", role="담당공무원", forms=["노다은"]),
        dict(type="RRN", value="400808 - 2765432", role="사망자", forms=["400808 - 2765432"]),
        dict(type="PHONE", value="010-이이삼삼-4455", role="연고자", forms=["010-이이삼삼-4455"]),
        dict(type="PHONE", value="061-555-0909", role="이장", forms=["061-555-0909"]),
        dict(type="PHONE", value="+82 10-7777-8888", role="손녀", forms=["+82 10-7777-8888"]),
        dict(type="PHONE", value="061-123-4568", role="기관", forms=["061-123-4568"]),
        dict(type="ADDR", value="전라남도 가온군 햇살면 들꽃길 12-3", role="사망자", keys=["들꽃길12-3"]),
    ],
))

DOCS.append(dict(
    id="D07", form="B-서울 나래구 사망자 처리 의뢰(외국인, 세로 라벨 변형)",
    blocks=[
        ("h", "서울특별시 나래구"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  무연고 외국인 사망자 장례 처리 의뢰"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("table", [
            ["사망자 성명", "응우옌반남"],
            ["외국인등록번호", "850101-5123456"],
            ["실거주지", "서울특별시 나래구 무지개길 8-2, 지하 1층"],
            ["신고인 성명", "황지민"],
            ["휴대폰", "010-3030-4040"],
        ], []),
        ("p", "2. 응우옌 반 남 씨는 2026. 10. 22. 오후 작업장 숙소에서 숨진 채 발견되었습니다. 신고인 황지민 씨는 같은 작업장 동료입니다."),
        ("p", "3. 본국 가족과는 연락이 닿지 않으며, 주한 대사관 담당 영사 연락처는 02-735-0000 입니다."),
        ("p", "4. 비용 1,234,567원, 사업자등록번호 123-45-67890, 2026-10-26 지급 예정."),
        ("p", "끝."),
        ("h", "나래구청장"),
        ("p", "기안자 주무관 오세린  검토자 팀장 맹지호  ☎ 02-2100-3456"),
    ],
    answer=[
        dict(type="NAME", value="응우옌반남", role="사망자", forms=["응우옌반남", "응우옌 반 남"]),
        dict(type="NAME", value="황지민", role="신고인", forms=["황지민"]),
        dict(type="NAME", value="오세린", role="담당공무원", forms=["오세린"]),
        dict(type="NAME", value="맹지호", role="담당공무원", forms=["맹지호"]),
        dict(type="RRN", value="850101-5123456", role="사망자", forms=["850101-5123456"]),
        dict(type="PHONE", value="010-3030-4040", role="신고인", forms=["010-3030-4040"]),
        dict(type="PHONE", value="02-735-0000", role="영사", forms=["02-735-0000"]),
        dict(type="PHONE", value="02-2100-3456", role="기관", forms=["02-2100-3456"]),
        dict(type="ADDR", value="서울특별시 나래구 무지개길 8-2, 지하 1층", role="사망자", keys=["무지개길8-2"]),
    ],
))

DOCS.append(dict(
    id="D08", form="A-가상구 희망복지지원단 의뢰(의뢰인·협조자)",
    blocks=[
        ("h", "가 상 구"),
        ("p", "수신  나눔과나눔 이사장"),
        ("t", "제목  공영장례 지원 의뢰"),
        ("p", "1. 관련: 복지정책과-12345(2026-10-24)"),
        ("table", [
            ["대상자 성명", "오말순", "주민등록번호", "380214-2112233"],
            ["주소", "서울특별시 가상구 예시로 77-1", "", ""],
            ["연고자", "배수진 (딸)", "연락처(연고자)", "0505-123-4567"],
            ["의뢰인", "가상구 희망복지지원단 팀장 선우진", "", ""],
        ], [((1, 1), (3, 1)), ((1, 3), (3, 3))]),
        ("p", "2. 오 말 순 님은 2026. 10. 23. 오후 병원에서 숨졌습니다. 딸 배수진 씨는 오랫동안 연락이 끊겼던 상태로, 말순 씨의 장례를 맡기 어렵다고 하였습니다."),
        ("p", "3. 오 씨는 생전에 서울특별시 가상구 예시로 77-1 에서 혼자 살았으며, 배수진 씨의 휴대폰 010-8282-1004 로도 연락이 가능합니다."),
        ("p", "4. 장례비 1,234,567원 (사업자등록번호 123-45-67890), 2026-10-26 오후 집행."),
        ("p", "끝."),
        ("h", "가상구청장"),
        ("p", "주무관 박민수  팀장 선우진  대표전화 1588-0000  전송 02-2600-1299"),
    ],
    answer=[
        dict(type="NAME", value="오말순", role="사망자", forms=["오말순", "오 말 순", "말순", "오 씨"]),
        dict(type="NAME", value="배수진", role="연고자", forms=["배수진"]),
        dict(type="NAME", value="선우진", role="담당공무원", forms=["선우진"]),
        dict(type="NAME", value="박민수", role="담당공무원", forms=["박민수"]),
        dict(type="RRN", value="380214-2112233", role="사망자", forms=["380214-2112233"]),
        dict(type="PHONE", value="0505-123-4567", role="연고자", forms=["0505-123-4567"]),
        dict(type="PHONE", value="010-8282-1004", role="연고자", forms=["010-8282-1004"]),
        dict(type="PHONE", value="1588-0000", role="기관", forms=["1588-0000"]),
        dict(type="PHONE", value="02-2600-1299", role="기관", forms=["02-2600-1299"]),
        dict(type="ADDR", value="서울특별시 가상구 예시로 77-1", role="사망자", keys=["예시로77-1"]),
    ],
))

HWPX_IDS = {"D03", "D08"}
FAX_FLIP_IDS = {"D02", "D07"}


# ---------------------------------------------------------------- 출력 함수
def to_markdown(doc) -> str:
    lines = []
    for b in doc["blocks"]:
        kind = b[0]
        if kind == "h":
            lines.append(f"## {b[1]}")
        elif kind == "t":
            lines.append(f"**{b[1]}**")
        elif kind == "p":
            lines.append(b[1].strip())
        elif kind == "table":
            rows = b[1]
            n = max(len(r) for r in rows)
            lines.append("| " + " | ".join(rows[0] + [""] * (n - len(rows[0]))) + " |")
            lines.append("|" + "---|" * n)
            for r in rows[1:]:
                lines.append("| " + " | ".join(r + [""] * (n - len(r))) + " |")
        lines.append("")
    return "\n".join(lines)


def make_pdf(doc, path: Path):
    if not FONT:
        sys.exit("한글 글꼴을 찾지 못했습니다. FAKE_FONT 환경 변수에 .ttf 글꼴 경로를 주세요.")
    pdfmetrics.registerFont(TTFont("KR", FONT))
    st_p = ParagraphStyle("p", fontName="KR", fontSize=10, leading=15)
    st_h = ParagraphStyle("h", fontName="KR", fontSize=15, leading=20, alignment=1)
    st_t = ParagraphStyle("t", fontName="KR", fontSize=11, leading=16)
    st_c = ParagraphStyle("c", fontName="KR", fontSize=9.5, leading=13)
    story = []
    for b in doc["blocks"]:
        kind = b[0]
        if kind == "h":
            story += [Spacer(1, 3 * mm), Paragraph(b[1], st_h), Spacer(1, 3 * mm)]
        elif kind == "t":
            story += [Paragraph(b[1], st_t), Spacer(1, 2 * mm)]
        elif kind == "p":
            txt = b[1].replace("  ", "&nbsp;&nbsp;")
            story.append(Paragraph(txt, st_p))
        elif kind == "table":
            rows, spans = b[1], b[2]
            n = max(len(r) for r in rows)
            data = [[Paragraph(c, st_c) for c in (r + [""] * (n - len(r)))] for r in rows]
            width = 170 * mm
            if n == 4:
                cw = [28 * mm, 62 * mm, 28 * mm, 52 * mm]
            elif n == 2:
                cw = [40 * mm, 130 * mm]
            else:
                cw = [width / n] * n
                cw = [26 * mm, 20 * mm, 22 * mm, 30 * mm, 46 * mm, 26 * mm][:n]
            t = Table(data, colWidths=cw)
            style = [("GRID", (0, 0), (-1, -1), 0.6, colors.black),
                     ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                     ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]
            for s in spans:
                style.append(("SPAN", s[0], s[1]))
            t.setStyle(TableStyle(style))
            story += [Spacer(1, 2 * mm), t, Spacer(1, 3 * mm)]
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=15 * mm).build(story)


def render_gray(pdf: Path, dpi: int) -> list[Image.Image]:
    out = []
    with fitz.open(pdf) as d:
        for page in d:
            pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            out.append(Image.frombytes("L", (pix.width, pix.height), pix.samples))
    return out


def make_scan(pdf: Path, path: Path, rng: random.Random):
    pages = []
    for im in render_gray(pdf, 300):
        im = im.rotate(rng.uniform(-0.5, 0.5), resample=Image.BICUBIC, expand=False, fillcolor=255)
        im = im.filter(ImageFilter.GaussianBlur(0.6))
        a = np.asarray(im).astype(np.float32)
        a = a * 0.93 + 8 + np.random.default_rng(rng.randint(0, 10**6)).normal(0, 7, a.shape)
        pages.append(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)))
    out = fitz.open()
    for im in pages:
        import io
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=70)
        pg = out.new_page(width=595, height=842)
        pg.insert_image(pg.rect, stream=buf.getvalue())
    out.save(path)


def make_fax(pdf: Path, path: Path, rng: random.Random, flip: bool):
    ims = render_gray(pdf, 200)
    im = ims[0]
    im = im.rotate(rng.uniform(0.8, 1.5) * rng.choice([-1, 1]), resample=Image.BICUBIC, fillcolor=255)
    im = im.filter(ImageFilter.GaussianBlur(0.7))
    a = np.asarray(im).astype(np.float32)
    g = np.random.default_rng(rng.randint(0, 10**6))
    a = a + g.normal(0, 18, a.shape)
    bw = a < 150
    speck = g.random(a.shape) < 0.002          # 검은 점 잡음
    drop = g.random(a.shape) < 0.03            # 획이 끊기는 흰 점
    bw = (bw & ~drop) | speck
    # 팩스 특유의 가로 줄무늬 몇 개
    for y in g.integers(0, a.shape[0], 3):
        bw[y, :] |= g.random(a.shape[1]) < 0.25
    img = Image.fromarray(np.where(bw, 0, 255).astype(np.uint8)).convert("1", dither=Image.NONE)
    if flip:
        img = img.rotate(180)
    img.save(path, dpi=(200, 200))


def count_forms(text: str, item) -> int:
    import re
    if item["type"] == "ADDR":
        norm = re.sub(r"\s+", "", text)
        return max(norm.count(k) for k in item["keys"])
    return sum(text.count(f) for f in item["forms"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "src").mkdir(exist_ok=True)
    (OUT / "answers").mkdir(exist_ok=True)
    rng = random.Random(20261026)
    manifest = []
    for doc in DOCS:
        did = doc["id"]
        md = to_markdown(doc)
        (OUT / "src" / f"{did}.md").write_text(md, encoding="utf-8")
        pdf = OUT / f"{did}_text.pdf"
        make_pdf(doc, pdf)
        files = {"text": pdf.name}
        if did in HWPX_IDS:
            hw = OUT / f"{did}_hwpx.hwpx"
            r = subprocess.run([str(KORDOC), "generate", str(OUT / "src" / f"{did}.md"), "-o", str(hw)],
                               capture_output=True, text=True)
            if r.returncode == 0 and hw.exists():
                files["hwpx"] = hw.name
            else:
                print(f"{did} hwpx 생성 실패 rc={r.returncode}", file=sys.stderr)
        scan = OUT / f"{did}_scan.pdf"
        make_scan(pdf, scan, rng)
        files["scan"] = scan.name
        fax = OUT / f"{did}_fax.png"
        make_fax(pdf, fax, rng, did in FAX_FLIP_IDS)
        files["fax"] = fax.name
        with fitz.open(pdf) as d:
            npages = d.page_count
        answer = {
            "doc": did, "form": doc["form"], "pages": npages, "files": files,
            "fax_flipped": did in FAX_FLIP_IDS,
            "items": [dict(it, count=count_forms(md, it)) for it in doc["answer"]],
            "must_not": COMMON_MUST_NOT + doc.get("must_not_extra", []),
        }
        (OUT / "answers" / f"{did}.answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=1), encoding="utf-8")
        manifest.append((did, npages, list(files)))
    for m in manifest:
        print(m)


if __name__ == "__main__":
    main()
