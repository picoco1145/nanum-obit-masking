"""이름 인식 모델(NER) 보완 단계 (지시서 5절 ⑤).

모델: atonlee/koelectra-ko-pii-ner (KoELECTRA-small-v3, apache-2.0, 약 14M 매개변수).
모델 폴더에서만 읽는다(local_files_only). 처리 중 외부 접속을 하지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

HANGUL_NAME = re.compile(r"^[가-힣]{2,4}$")
_PIPE = None


def _pipe(model_dir: Path):
    global _PIPE
    if _PIPE is None:
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
        tok = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        mdl = AutoModelForTokenClassification.from_pretrained(str(model_dir), local_files_only=True)
        _PIPE = pipeline("token-classification", model=mdl, tokenizer=tok,
                         aggregation_strategy="simple", device=-1)
    return _PIPE


def _plain(text: str) -> str:
    """표 마크업(<td> 등)과 파이프를 같은 길이의 공백으로 바꿔 위치를 유지한다."""
    t = re.sub(r"<[^>\n]{1,40}>", lambda m: " " * len(m.group(0)), text)
    t = re.sub(r"(?<!\\)\|", " ", t)
    # OCR이 '2. 오말순'을 '2오말순'으로 붙여 읽으면 모델이 이름을 놓친다. 줄 머리 번호를 공백으로 바꾼다.
    t = re.sub(r"(?m)^(\d{1,2}[.:]?)(?=[가-힣])", lambda m: " " * len(m.group(1)), t)
    return t


def find(text: str, model_dir: Path, stopwords: set[str], use_address: bool = False,
         threshold: float = 0.6) -> list[dict]:
    """반환: [{start, end, kind(NAME/ADDR), word, score, masked(bool)}]"""
    nlp = _pipe(model_dir)
    plain = _plain(text)
    out = []
    pos = 0
    for line in plain.split("\n"):
        ls = pos
        pos += len(line) + 1
        if not line.strip() or not re.search(r"[가-힣]", line):
            continue
        # 모델 입력 길이(512 토큰)를 넘지 않게 300자 단위로 자른다
        for cs in range(0, len(line), 300):
            chunk = line[cs:cs + 300]
            for ent in nlp(chunk):
                grp = ent["entity_group"]
                s, e = ls + cs + ent["start"], ls + cs + ent["end"]
                # 앞뒤 공백 정리
                while s < e and text[s].isspace():
                    s += 1
                while e > s and text[e - 1].isspace():
                    e -= 1
                word = text[s:e]
                score = float(ent["score"])
                if grp == "NAME":
                    w = word
                    # 뒤에 붙은 호칭·조사 떼기
                    m = re.match(r"^([가-힣]{2,4}?)(님|씨|은|는|이|가|을|를|의)?$", w)
                    if m:
                        w = m.group(1)
                        e = s + len(w)
                    if not HANGUL_NAME.match(w) or w in stopwords:
                        continue
                    out.append({"start": s, "end": e, "kind": "NAME", "word": w, "score": score,
                                "masked": score >= threshold})
                elif grp == "ADDRESS" and use_address:
                    if len(word.replace(" ", "")) < 6 or not re.search(r"\d", word):
                        continue
                    out.append({"start": s, "end": e, "kind": "ADDR", "word": word, "score": score,
                                "masked": score >= threshold})
    return out


def load_stopwords(path: Path) -> set[str]:
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()}
