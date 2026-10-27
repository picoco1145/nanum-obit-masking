"""학습 실험용 새 가짜 공문 세트(N01~N12)를 만든다.

기존 26건(make_fake.py)과 겹치지 않게 새 양식·새 칸 이름·새 오독 유형·새 표현을 넣었다.
모든 이름·번호·주소는 지어낸 값이다. 실제 사람 정보는 쓰지 않는다.

- 학습 절반(L): N01~N06  — 처음 성적을 잰 뒤 이 절반의 오답만 오답 노트에 넣는다.
- 시험 절반(H): N07~N12  — 학습에 쓰지 않고, 학습 후 성적만 잰다.
  N07~N11은 학습 절반과 같은 종류의 새 요소를 다른 값·다른 형식으로 담았고,
  N12는 학습 절반에 없는 양식(요양원)이라 일반화가 안 되는 경우를 보려고 넣었다.

결과: tests/fake2/<ID>_<형식>.<확장자>, tests/fake2/src/<ID>.md, tests/fake2/answers/<ID>.answer.json
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import fitz  # pymupdf
import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_fake as mf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fake2"
COMMON_MUST_NOT = mf.COMMON_MUST_NOT

DOCS = []

# ---------------------------------------------------------------- 학습 절반 (L)
DOCS.append(dict(
    id="N01", half="L", fmt="text", form="E-가람경찰서 변사사건 결과 통보(새 양식)",
    blocks=[
        ("h", "가람경찰서"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  변사사건 처리 결과 통보 및 무연고 장례 협조 요청"),
        ("p", "1. 관련: 형사과-2231(2026-10-19)"),
        ("p", "2. 관내 변사사건의 검안이 끝나 아래와 같이 통보합니다."),
        ("table", [
            ["변사자", "추봉식", "생년월일", "1951. 4. 9."],
            ["주민등록번호", "510409-1******", "주민등록지", "부산광역시 가람구 솔바람로 21-3"],
            ["최초발견자", "명지숙 (집주인)", "긴급연락처", "010-4411-2233"],
            ["인수자", "추봉남 (형, 인수 거부)", "사건번호", "변사-2026-0451"],
        ], []),
        ("p", "3. 변사자는 2026. 10. 17. 오후 자택에서 숨진 채 발견되었고, 검안 결과 범죄 혐의점은 없습니다."),
        ("p", "4. 망 추봉식의 형 추봉남 씨(☎ 051-303-4040)는 시신 인수를 거부하였습니다."),
        ("p", "5. 최초발견자 명지숙 씨는 월세가 밀려 방문하였다고 진술하였습니다."),
        ("p", "6. 장례비 1,234,567원(사업자등록번호 123-45-67890), 처리 예정일 2026-10-26."),
        ("p", "끝."),
        ("h", "가람경찰서장"),
        ("p", "형사과 경위 왕도현  ☎ 051-900-1122  팩스 051-900-1199"),
    ],
    answer=[
        dict(type="NAME", value="추봉식", role="사망자", forms=["추봉식"]),
        dict(type="NAME", value="명지숙", role="신고인", forms=["명지숙"]),
        dict(type="NAME", value="추봉남", role="연고자", forms=["추봉남"]),
        dict(type="NAME", value="왕도현", role="담당공무원", forms=["왕도현"]),
        dict(type="RRN", value="510409-1******", role="사망자", forms=["510409-1******"]),
        dict(type="PHONE", value="010-4411-2233", role="신고인", forms=["010-4411-2233"]),
        dict(type="PHONE", value="051-303-4040", role="연고자", forms=["051-303-4040"]),
        dict(type="PHONE", value="051-900-1122", role="기관", forms=["051-900-1122"]),
        dict(type="PHONE", value="051-900-1199", role="기관", forms=["051-900-1199"]),
        dict(type="ADDR", value="부산광역시 가람구 솔바람로 21-3", role="사망자", keys=["솔바람로21-3"]),
    ],
    must_not_extra=["변사-2026-0451", "1951. 4. 9.", "형사과-2231"],
))

DOCS.append(dict(
    id="N02", half="L", fmt="fax", form="F-가온대학교병원 무연고 사망 환자 의뢰(새 양식)",
    blocks=[
        ("h", "가온대학교병원 사회사업팀"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  무연고 사망 환자 시신 처리 의뢰"),
        ("p", "1. 관련: 사회사업팀-778"),
        ("p", "2. 아래 환자가 입원 중 사망하였으나 연고자가 확인되지 않아 장례 지원을 의뢰합니다."),
        ("table", [
            ["환자명", "봉말례", "병록번호", "2026-001234"],
            ["생년월일", "1944-02-17", "성별", "여"],
            ["입원 전 주소", "대구광역시 가온구 달빛로9길 14", "", ""],
            ["보호자명", "나봄 (사회복지사)", "비상연락처", "010-6262-7373"],
        ], [((1, 2), (3, 2))]),
        ("p", "3. 봉말례 환자는 2026. 10. 16. 오전 병동에서 사망하였습니다."),
        ("p", "4. 입원 당시 본인 휴대폰 공일공 칠칠팔팔 구구공공 은 정지된 상태입니다."),
        ("p", "5. 장례비 1,234,567원(사업자등록번호 123-45-67890), 2026-10-26 지급 예정."),
        ("p", "끝."),
        ("h", "가온대학교병원장"),
        ("p", "의료사회복지사 표은서  전화 053-420-5555  팩스 053-420-5599"),
    ],
    answer=[
        dict(type="NAME", value="봉말례", role="사망자", forms=["봉말례"]),
        dict(type="NAME", value="나봄", role="연고자", forms=["나봄"]),
        dict(type="NAME", value="표은서", role="담당공무원", forms=["표은서"]),
        dict(type="PHONE", value="010-6262-7373", role="연고자", forms=["010-6262-7373"]),
        dict(type="PHONE", value="010-7788-9900", role="사망자", forms=["공일공 칠칠팔팔 구구공공"]),
        dict(type="PHONE", value="053-420-5555", role="기관", forms=["053-420-5555"]),
        dict(type="PHONE", value="053-420-5599", role="기관", forms=["053-420-5599"]),
        dict(type="ADDR", value="대구광역시 가온구 달빛로9길 14", role="사망자", keys=["달빛로9길14"]),
    ],
    must_not_extra=["2026-001234", "1944-02-17"],
))

DOCS.append(dict(
    id="N03", half="L", fmt="scan", form="A변형-가상구 통보(고(故) 표기, 괄호 속 이름)",
    blocks=[
        ("h", "가 상 구"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  무연고 사망자 공영장례 지원 요청"),
        ("p", "1. 관련: 복지정책과-12345(2026-10-22)"),
        ("table", [
            ["성 명", "엄태식", "주민등록번호", "490707-1567890"],
            ["주 소", "서울특별시 가상구 버들로 45, 2층", "", ""],
        ], [((1, 1), (3, 1))]),
        ("p", "2. 고(故) 엄태식 님은 2026. 10. 20. 오후 자택에서 숨진 채 발견되었습니다."),
        ("p", "3. 최초 신고자(옆집 주민 함소라)가 악취가 난다며 112에 신고하였습니다."),
        ("p", "4. 연고자(차녀, 엄지은)는 연락이 끊긴 지 오래되어 장례를 맡기 어렵다고 하였습니다."),
        ("p", "5. 장례비 1,234,567원(사업자등록번호 123-45-67890), 발인 2026-10-26."),
        ("p", "끝."),
        ("h", "가상구청장"),
        ("p", "주무관 노하린  팀장 정예준  전화 02-2600-1235"),
    ],
    answer=[
        dict(type="NAME", value="엄태식", role="사망자", forms=["엄태식"]),
        dict(type="NAME", value="함소라", role="신고인", forms=["함소라"]),
        dict(type="NAME", value="엄지은", role="연고자", forms=["엄지은"]),
        dict(type="NAME", value="노하린", role="담당공무원", forms=["노하린"]),
        dict(type="NAME", value="정예준", role="담당공무원", forms=["정예준"]),
        dict(type="RRN", value="490707-1567890", role="사망자", forms=["490707-1567890"]),
        dict(type="PHONE", value="02-2600-1235", role="기관", forms=["02-2600-1235"]),
        dict(type="ADDR", value="서울특별시 가상구 버들로 45, 2층", role="사망자", keys=["버들로45"]),
    ],
    must_not_extra=["112"],
))

DOCS.append(dict(
    id="N04", half="L", fmt="text", form="D-가람구 외국인 사망자 통보(로마자 이름, 영문 주소)",
    blocks=[
        ("h", "부산광역시 가람구"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  외국인 무연고 사망자 장례 지원 요청"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("table", [
            ["성명(영문)", "NGUYEN THI LAN"],
            ["성명(한글)", "응우옌티란"],
            ["외국인등록번호", "870615-6234567"],
            ["체류지", "12, Haesol-ro 3-gil, Garam-gu, Busan"],
            ["고용주", "가람수산 대표 맹석구"],
            ["연락처", "010-7070-1212"],
        ], []),
        ("p", "2. 응우옌 티 란 씨는 2026. 10. 18. 오후 기숙사에서 숨진 채 발견되었습니다."),
        ("p", "3. 같은 기숙사 동료 왕샤오밍(王小明) 씨가 처음 발견하였습니다."),
        ("p", "4. 본국 가족과는 연락이 닿지 않았습니다. 비용 1,234,567원, 사업자등록번호 123-45-67890, 2026-10-26 지급 예정."),
        ("p", "끝."),
        ("h", "부산광역시 가람구청장"),
        ("p", "주무관 윤하늘  전화 051-600-7001"),
    ],
    answer=[
        dict(type="NAME", value="NGUYEN THI LAN", role="사망자", forms=["NGUYEN THI LAN"]),
        dict(type="NAME", value="응우옌티란", role="사망자", forms=["응우옌티란", "응우옌 티 란"]),
        dict(type="NAME", value="맹석구", role="고용주", forms=["맹석구"]),
        dict(type="NAME", value="왕샤오밍", role="신고인", forms=["왕샤오밍", "王小明"]),
        dict(type="NAME", value="윤하늘", role="담당공무원", forms=["윤하늘"]),
        dict(type="RRN", value="870615-6234567", role="사망자", forms=["870615-6234567"]),
        dict(type="PHONE", value="010-7070-1212", role="고용주", forms=["010-7070-1212"]),
        dict(type="PHONE", value="051-600-7001", role="기관", forms=["051-600-7001"]),
        dict(type="ADDR", value="12, Haesol-ro 3-gil, Garam-gu, Busan", role="사망자", keys=["Haesol-ro3-gil"]),
    ],
    must_not_extra=["가람수산"],
))

DOCS.append(dict(
    id="N05", half="L", fmt="scan", form="C변형-나래구 통보(O·l 오독이 섞인 재입력 문서)",
    blocks=[
        ("h", "서울특별시 나래구"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  무연고 사망자 발생 통보"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("p", "2. 사망자 인적사항(팩스 원본을 다시 입력한 것임)"),
        ("p", "   가. 고인 : 석만길 (남, 73세)"),
        ("p", "   나. 주민등록번호 : 530303-l******"),
        ("p", "   다. 주소 : 서울특별시 나래구 꽃담길 7-1"),
        ("p", "   라. 연고자 : 석미란 (여동생)  연락처 : O1O-3456-7788"),
        ("p", "3. 석만길 님은 2026. 10. 19. 오후 숨진 채 발견되었으며, 여동생 석미란 씨는 장례 참석이 어렵다고 하였습니다."),
        ("p", "4. 비용 1,234,567원, 사업자등록번호 123-45-67890, 2026-10-26 지급."),
        ("p", "끝."),
        ("h", "나래구청장"),
        ("p", "주무관 배서윤  ☎ 02-2100-3457"),
    ],
    answer=[
        dict(type="NAME", value="석만길", role="사망자", forms=["석만길"]),
        dict(type="NAME", value="석미란", role="연고자", forms=["석미란"]),
        dict(type="NAME", value="배서윤", role="담당공무원", forms=["배서윤"]),
        dict(type="RRN", value="530303-1******", role="사망자", forms=["530303-l******"]),
        dict(type="PHONE", value="010-3456-7788", role="연고자", forms=["O1O-3456-7788"]),
        dict(type="PHONE", value="02-2100-3457", role="기관", forms=["02-2100-3457"]),
        dict(type="ADDR", value="서울특별시 나래구 꽃담길 7-1", role="사망자", keys=["꽃담길7-1"]),
    ],
))

DOCS.append(dict(
    id="N06", half="L", fmt="fax", form="C변형-가온군 통보(망 표기, 숫자를 한 칸씩 띄운 번호)",
    blocks=[
        ("h", "전라남도 가온군"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  무연고사망자 장례 지원 요청"),
        ("p", "1. 관련: 복지정책과-12345(2026-10-23)"),
        ("p", "2. 망인 인적사항"),
        ("p", "   ○ 망인 : 곽순애, 여, 1939년생"),
        ("p", "   ○ 주민번호 : 391120-2345612"),
        ("p", "   ○ 상주 : 곽두만 (남동생)"),
        ("p", "3. 망 곽순애 님은 전라남도 가온군 솔내면 동백길 33 자택에서 사망하였습니다."),
        ("p", "4. 남동생 곽두만 씨의 연락처는 0 1 0 8 8 7 7 6 6 5 5 입니다."),
        ("p", "5. 비용 1,234,567원, 사업자등록번호 123-45-67890, 처리일 2026-10-26."),
        ("p", "끝."),
        ("h", "가온군수"),
        ("p", "담당자 : 사회복지주무관 모아라   팩스 061-123-4569"),
    ],
    answer=[
        dict(type="NAME", value="곽순애", role="사망자", forms=["곽순애"]),
        dict(type="NAME", value="곽두만", role="연고자", forms=["곽두만"]),
        dict(type="NAME", value="모아라", role="담당공무원", forms=["모아라"]),
        dict(type="RRN", value="391120-2345612", role="사망자", forms=["391120-2345612"]),
        dict(type="PHONE", value="010-8877-6655", role="연고자", forms=["0 1 0 8 8 7 7 6 6 5 5"]),
        dict(type="PHONE", value="061-123-4569", role="기관", forms=["061-123-4569"]),
        dict(type="ADDR", value="전라남도 가온군 솔내면 동백길 33", role="사망자", keys=["동백길33"]),
    ],
))

# ---------------------------------------------------------------- 시험 절반 (H)
DOCS.append(dict(
    id="N07", half="H", fmt="scan", form="E-나래경찰서 변사사건 결과 통보(새 양식, 다른 값)",
    blocks=[
        ("h", "나래경찰서"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  변사사건 처리 결과 통보"),
        ("p", "1. 관련: 형사과-3310"),
        ("table", [
            ["변사자", "하옥분", "생년월일", "1947. 12. 1."],
            ["주민등록번호", "471201-2******", "주민등록지", "서울특별시 나래구 은행나무로 88"],
            ["최초발견자", "선우경태 (요양보호사)", "긴급연락처", "010-2323-4545"],
            ["인수자", "하정민 (조카)", "사건번호", "변사-2026-0517"],
        ], []),
        ("p", "2. 변사자는 2026. 10. 21. 오전 자택에서 발견되었습니다. 망 하옥분의 조카 하정민 씨는 장례를 치를 형편이 아니라고 하였습니다."),
        ("p", "3. 장례비 1,234,567원(사업자등록번호 123-45-67890), 2026-10-26 지급 예정."),
        ("p", "끝."),
        ("h", "나래경찰서장"),
        ("p", "형사과 경사 차은결  ☎ 02-3400-5566"),
    ],
    answer=[
        dict(type="NAME", value="하옥분", role="사망자", forms=["하옥분"]),
        dict(type="NAME", value="선우경태", role="신고인", forms=["선우경태"]),
        dict(type="NAME", value="하정민", role="연고자", forms=["하정민"]),
        dict(type="NAME", value="차은결", role="담당공무원", forms=["차은결"]),
        dict(type="RRN", value="471201-2******", role="사망자", forms=["471201-2******"]),
        dict(type="PHONE", value="010-2323-4545", role="신고인", forms=["010-2323-4545"]),
        dict(type="PHONE", value="02-3400-5566", role="기관", forms=["02-3400-5566"]),
        dict(type="ADDR", value="서울특별시 나래구 은행나무로 88", role="사망자", keys=["은행나무로88"]),
    ],
    must_not_extra=["변사-2026-0517", "1947. 12. 1.", "형사과-3310"],
))

DOCS.append(dict(
    id="N08", half="H", fmt="text", form="F-나래의료원 무연고 사망 환자 의뢰(새 양식, 다른 값)",
    blocks=[
        ("h", "나래의료원 공공의료팀"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  무연고 사망 환자 장례 지원 의뢰"),
        ("table", [
            ["환자명", "감영철", "병록번호", "2026-004567"],
            ["입원 전 주소", "인천광역시 가나구 노을로 55, 302호", "", ""],
            ["보호자명", "도란 (여동생)", "비상연락처", "010-9191-2828"],
        ], [((1, 1), (3, 1))]),
        ("p", "1. 감영철 님은 2026. 10. 22. 새벽 병실에서 사망하였습니다. 여동생 도란 씨는 장례비를 감당할 수 없다고 하였습니다."),
        ("p", "2. 비용 1,234,567원(사업자등록번호 123-45-67890), 2026-10-26 지급."),
        ("p", "끝."),
        ("h", "나래의료원장"),
        ("p", "의료사회복지사 길보람  전화 032-560-7777"),
    ],
    answer=[
        dict(type="NAME", value="감영철", role="사망자", forms=["감영철"]),
        dict(type="NAME", value="도란", role="연고자", forms=["도란"]),
        dict(type="NAME", value="길보람", role="담당공무원", forms=["길보람"]),
        dict(type="PHONE", value="010-9191-2828", role="연고자", forms=["010-9191-2828"]),
        dict(type="PHONE", value="032-560-7777", role="기관", forms=["032-560-7777"]),
        dict(type="ADDR", value="인천광역시 가나구 노을로 55, 302호", role="사망자", keys=["노을로55"]),
    ],
    must_not_extra=["2026-004567"],
))

DOCS.append(dict(
    id="N09", half="H", fmt="fax", form="A변형-가나구 통보(고(故) 표기, 괄호 속 이름, 다른 값)",
    blocks=[
        ("h", "인천광역시 가나구"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  무연고 사망자 공영장례 지원 요청"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("table", [
            ["성 명", "반정숙", "주민등록번호", "520918-2678901"],
            ["주 소", "인천광역시 가나구 갈매기로 19", "", ""],
        ], [((1, 1), (3, 1))]),
        ("p", "2. 고(故) 반정숙 님은 2026. 10. 21. 오후 숨진 채 발견되었습니다."),
        ("p", "3. 최초 신고자(통장 육재희)가 우편물이 쌓였다며 신고하였습니다."),
        ("p", "4. 연고자(장남, 반기석)는 장례 참석이 어렵다고 하였습니다."),
        ("p", "5. 비용 1,234,567원, 사업자등록번호 123-45-67890, 2026-10-26 지급."),
        ("p", "끝."),
        ("h", "가나구청장"),
        ("p", "주무관 소예린  전화 032-440-1235"),
    ],
    answer=[
        dict(type="NAME", value="반정숙", role="사망자", forms=["반정숙"]),
        dict(type="NAME", value="육재희", role="신고인", forms=["육재희"]),
        dict(type="NAME", value="반기석", role="연고자", forms=["반기석"]),
        dict(type="NAME", value="소예린", role="담당공무원", forms=["소예린"]),
        dict(type="RRN", value="520918-2678901", role="사망자", forms=["520918-2678901"]),
        dict(type="PHONE", value="032-440-1235", role="기관", forms=["032-440-1235"]),
        dict(type="ADDR", value="인천광역시 가나구 갈매기로 19", role="사망자", keys=["갈매기로19"]),
    ],
))

DOCS.append(dict(
    id="N10", half="H", fmt="scan", form="D-가온구 외국인 사망자 통보(로마자 이름, 영문 주소, 다른 값)",
    blocks=[
        ("h", "대구광역시 가온구"),
        ("p", "수신  사단법인 나눔과나눔"),
        ("t", "제목  외국인 무연고 사망자 장례 지원 요청"),
        ("table", [
            ["성명(영문)", "MARIA SANTOS"],
            ["성명(한글)", "마리아산토스"],
            ["외국인등록번호", "790202-6345678"],
            ["체류지", "33, Eunha-ro 5-gil, Gaon-gu, Daegu"],
            ["고용주", "가온봉제 대표 피정우"],
            ["연락처", "010-5050-3131"],
        ], []),
        ("p", "1. 마리아 산토스 씨는 2026. 10. 20. 오후 숙소에서 숨진 채 발견되었습니다."),
        ("p", "2. 동료 왕리핑(王麗萍) 씨가 119에 신고하였습니다."),
        ("p", "3. 비용 1,234,567원, 사업자등록번호 123-45-67890, 2026-10-26 지급 예정."),
        ("p", "끝."),
        ("h", "대구광역시 가온구청장"),
        ("p", "주무관 진나래  전화 053-600-2001"),
    ],
    answer=[
        dict(type="NAME", value="MARIA SANTOS", role="사망자", forms=["MARIA SANTOS"]),
        dict(type="NAME", value="마리아산토스", role="사망자", forms=["마리아산토스", "마리아 산토스"]),
        dict(type="NAME", value="피정우", role="고용주", forms=["피정우"]),
        dict(type="NAME", value="왕리핑", role="신고인", forms=["왕리핑", "王麗萍"]),
        dict(type="NAME", value="진나래", role="담당공무원", forms=["진나래"]),
        dict(type="RRN", value="790202-6345678", role="사망자", forms=["790202-6345678"]),
        dict(type="PHONE", value="010-5050-3131", role="고용주", forms=["010-5050-3131"]),
        dict(type="PHONE", value="053-600-2001", role="기관", forms=["053-600-2001"]),
        dict(type="ADDR", value="33, Eunha-ro 5-gil, Gaon-gu, Daegu", role="사망자", keys=["Eunha-ro5-gil"]),
    ],
    must_not_extra=["가온봉제", "119"],
))

DOCS.append(dict(
    id="N11", half="H", fmt="text", form="C변형-가람구 통보(O·l 오독, 띄운 번호, 다른 값)",
    blocks=[
        ("h", "부산광역시 가람구"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  무연고 사망자 발생 통보"),
        ("p", "1. 관련: 복지정책과-12345"),
        ("p", "2. 사망자 인적사항(팩스 원본을 다시 입력한 것임)"),
        ("p", "   가. 고인 : 우봉래 (남, 80세)"),
        ("p", "   나. 주민등록번호 : 461010-l******"),
        ("p", "   다. 주소 : 부산광역시 가람구 파도길 21"),
        ("p", "   라. 연고자 : 우경미 (딸)  연락처 : O1O-6543-2109"),
        ("p", "3. 우봉래 님의 딸 우경미 씨는 다른 연락처 0 1 0 4 4 3 3 2 2 1 1 로도 연락할 수 있다고 하였습니다."),
        ("p", "4. 비용 1,234,567원, 사업자등록번호 123-45-67890, 2026-10-26 지급."),
        ("p", "끝."),
        ("h", "부산광역시 가람구청장"),
        ("p", "주무관 엄다솜  전화 051-600-7002"),
    ],
    answer=[
        dict(type="NAME", value="우봉래", role="사망자", forms=["우봉래"]),
        dict(type="NAME", value="우경미", role="연고자", forms=["우경미"]),
        dict(type="NAME", value="엄다솜", role="담당공무원", forms=["엄다솜"]),
        dict(type="RRN", value="461010-1******", role="사망자", forms=["461010-l******"]),
        dict(type="PHONE", value="010-6543-2109", role="연고자", forms=["O1O-6543-2109"]),
        dict(type="PHONE", value="010-4433-2211", role="연고자", forms=["0 1 0 4 4 3 3 2 2 1 1"]),
        dict(type="PHONE", value="051-600-7002", role="기관", forms=["051-600-7002"]),
        dict(type="ADDR", value="부산광역시 가람구 파도길 21", role="사망자", keys=["파도길21"]),
    ],
))

DOCS.append(dict(
    id="N12", half="H", fmt="fax", form="G-요양원 입소자 사망 통보(학습 절반에 없는 양식)",
    blocks=[
        ("h", "가상요양원"),
        ("p", "수신  나눔과나눔"),
        ("t", "제목  입소자 사망 및 무연고 장례 지원 요청"),
        ("table", [
            ["입소자", "탁순임", "입소번호", "가상-2019-031"],
            ["입소 전 주소", "경기도 가상시 은빛로 102", "", ""],
            ["책임자", "모은성 (사무국장)", "사무실", "031-777-8899"],
        ], [((1, 1), (3, 1))]),
        ("p", "1. 입소자 탁순임 어르신은 2026. 10. 23. 새벽 요양원에서 별세하였습니다."),
        ("p", "2. 가족관계 확인 결과 연고자가 없으며, 책임자 모은성 사무국장이 장례 절차를 문의하였습니다."),
        ("p", "3. 비용 1,234,567원(사업자등록번호 123-45-67890), 2026-10-26 지급 예정."),
        ("p", "끝."),
        ("h", "가상요양원장"),
        ("p", "생활지원팀 금소율  전화 031-777-8800"),
    ],
    answer=[
        dict(type="NAME", value="탁순임", role="사망자", forms=["탁순임"]),
        dict(type="NAME", value="모은성", role="책임자", forms=["모은성"]),
        dict(type="NAME", value="금소율", role="담당자", forms=["금소율"]),
        dict(type="PHONE", value="031-777-8899", role="책임자", forms=["031-777-8899"]),
        dict(type="PHONE", value="031-777-8800", role="기관", forms=["031-777-8800"]),
        dict(type="ADDR", value="경기도 가상시 은빛로 102", role="사망자", keys=["은빛로102"]),
    ],
    must_not_extra=["가상-2019-031"],
))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "src").mkdir(exist_ok=True)
    (OUT / "answers").mkdir(exist_ok=True)
    rng = random.Random(20261027)
    manifest = []
    for doc in DOCS:
        did = doc["id"]
        md = mf.to_markdown(doc)
        (OUT / "src" / f"{did}.md").write_text(md, encoding="utf-8")
        tmp_pdf = OUT / "src" / f"{did}_base.pdf"
        mf.make_pdf(doc, tmp_pdf)
        fmt = doc["fmt"]
        if fmt == "text":
            target = OUT / f"{did}_text.pdf"
            target.write_bytes(tmp_pdf.read_bytes())
        elif fmt == "scan":
            target = OUT / f"{did}_scan.pdf"
            mf.make_scan(tmp_pdf, target, rng)
        else:
            target = OUT / f"{did}_fax.png"
            mf.make_fax(tmp_pdf, target, rng, flip=did == "N09")
        with fitz.open(tmp_pdf) as d:
            npages = d.page_count
        answer = {
            "doc": did, "form": doc["form"], "half": doc["half"], "pages": npages,
            "files": {fmt: target.name}, "fax_flipped": did == "N09",
            "items": [dict(it, count=max(1, mf.count_forms(md, it))) for it in doc["answer"]],
            "must_not": COMMON_MUST_NOT + doc.get("must_not_extra", []),
        }
        (OUT / "answers" / f"{did}.answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=1),
                                                             encoding="utf-8")
        manifest.append((did, doc["half"], fmt, npages))
    for m in manifest:
        print(m)


if __name__ == "__main__":
    main()
