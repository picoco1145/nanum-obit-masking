"""글자 읽기 (지시서 5절 ②). 결과는 표 행·열을 유지한 마크다운 텍스트 하나이다.

- HWP·HWPX·글자가 든 PDF: kordoc
- 스캔 PDF: kordoc --ocr (내장 PP-OCRv5 korean ONNX)
- 팩스·이미지: 8비트 회색조 → PaddleOCR(PP-OCRv5 korean, CPU) → 평균 신뢰도가 policy.yaml의
  fax_rotate_below(기본 0.8) 미만이면 180도 돌려 다시 읽기
  표 구조는 방법 A(kordoc --ocr)와 방법 B(글자 상자를 행으로 묶기) 중 고른다.
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
# kordoc 오프라인 래퍼. 환경 변수 NANUM_KORDOC에 래퍼 경로를 준다.
# 없으면 Windows에서는 app/kordoc-safe.cmd를, 그 밖의 운영체제에서는 PATH의 kordoc을 쓴다.
KORDOC = Path(os.environ.get("NANUM_KORDOC")
              or (ROOT / "app" / "kordoc-safe.cmd" if os.name == "nt" else shutil.which("kordoc") or "kordoc"))
_OCR = {}


def source_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".hwp":
        return "hwp"
    if ext == ".hwpx":
        return "hwpx"
    if ext == ".pdf":
        import pymupdf as fitz
        with fitz.open(path) as d:
            chars = sum(len(p.get_text().strip()) for p in d)
        return "pdf-text" if chars >= 30 else "pdf-ocr"
    if ext in (".png", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp"):
        return "fax"
    return "unknown"


def run_kordoc(path: Path, out_md: Path, ocr: bool, log: Path) -> str:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, KORDOC_NETGUARD_LOG=str(log))
    cmd = [str(KORDOC), str(path), "--silent", "--no-images", "-o", str(out_md)]
    if ocr:
        cmd.insert(2, "--ocr")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        # 오류 내용에 문서 글자가 섞일 수 있어 종료 코드만 남긴다
        raise RuntimeError(f"kordoc 실패(exit {r.returncode})")
    return out_md.read_text(encoding="utf-8")


# ---------------------------------------------------------------- PaddleOCR
def paddle(det: str = "mobile"):
    if det not in _OCR:
        from paddleocr import PaddleOCR
        # 검출 모델 이름을 주면 lang이 무시되므로 인식 모델(한국어)도 이름으로 지정한다
        kw = dict(text_detection_model_name=f"PP-OCRv5_{det}_det",
                  text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
                  use_doc_orientation_classify=False, use_doc_unwarping=False,
                  use_textline_orientation=False,
                  # 기본값(짧은 변 64 이상, 사실상 원본 크기)보다 긴 변 1600으로 줄였을 때 맥에서 정확도·속도가 나았다
                  text_det_limit_type="max", text_det_limit_side_len=1600)
        _OCR[det] = PaddleOCR(**kw)
    return _OCR[det]


def load_image(path: Path, prep: str) -> np.ndarray:
    """prep: gray8(지시서) | none(원본 그대로 RGB로만 바꿈)"""
    im = Image.open(path)
    if prep == "gray8":
        im = im.convert("L")
        arr = np.array(im)
        return np.stack([arr] * 3, axis=-1)
    return np.array(im.convert("RGB"))


def ocr_image(arr: np.ndarray, det: str = "mobile"):
    res = paddle(det).predict(arr)
    r = res[0]
    texts = list(r["rec_texts"])
    scores = [float(s) for s in r["rec_scores"]]
    boxes = [list(map(float, b)) for b in r["rec_boxes"]]  # x1,y1,x2,y2
    mean = float(np.mean(scores)) if scores else 0.0
    return texts, scores, boxes, mean


def rows_markdown(texts, boxes) -> str:
    """방법 B: 글자 상자를 y가 겹치는 것끼리 한 행으로 묶고 x 순으로 정렬한다."""
    items = sorted(zip(texts, boxes), key=lambda t: (t[1][1] + t[1][3]) / 2)
    rows: list[list] = []
    for t, b in items:
        cy = (b[1] + b[3]) / 2
        h = b[3] - b[1]
        if rows:
            last = rows[-1]
            ly1 = min(x[1][1] for x in last)
            ly2 = max(x[1][3] for x in last)
            overlap = min(ly2, b[3]) - max(ly1, b[1])
            if overlap > 0.5 * min(h, ly2 - ly1):
                last.append((t, b))
                continue
        rows.append([(t, b)])
    lines = []
    for r in rows:
        r.sort(key=lambda x: x[1][0])
        cells = [x[0].strip() for x in r]
        if len(cells) >= 2:
            lines.append("| " + " | ".join(cells) + " |")
        else:
            lines.append(cells[0])
    return "\n".join(lines) + "\n"


def read_fax(path: Path, work: Path, doc_id: str, log: Path, method: str = "B", det: str = "mobile",
             prep: str = "gray8", rotate_below: float = 0.8) -> tuple[str, dict]:
    info = {"rotated": False}
    t0 = time.process_time()
    arr = load_image(path, prep)
    texts, scores, boxes, mean = ocr_image(arr, det)
    info["mean_first"] = mean
    if mean < rotate_below:
        arr2 = np.ascontiguousarray(np.rot90(arr, 2))
        t2, s2, b2, m2 = ocr_image(arr2, det)
        info["mean_rot180"] = m2
        if m2 > mean:
            arr, texts, scores, boxes, mean = arr2, t2, s2, b2, m2
            info["rotated"] = True
    info["mean_conf"] = round(mean, 4)
    info["low_conf_lines"] = sum(1 for s in scores if s < 0.8)
    info["paddle_cpu_s"] = round(time.process_time() - t0, 2)
    if method == "A":
        # 고른 방향의 회색조 이미지를 PDF로 감싸 kordoc --ocr로 읽는다
        import pymupdf as fitz
        work.mkdir(parents=True, exist_ok=True)
        im = Image.fromarray(arr[:, :, 0])
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        w, h = im.size
        dpi = (Image.open(path).info.get("dpi") or (200, 200))[0] or 200
        doc = fitz.open()
        page = doc.new_page(width=w * 72 / dpi, height=h * 72 / dpi)
        page.insert_image(page.rect, stream=buf.getvalue())
        pdf = work / f"{doc_id}.fax.pdf"
        doc.save(pdf)
        md = run_kordoc(pdf, work / f"{doc_id}.md", True, log)
    else:
        md = rows_markdown(texts, boxes)
        (work / f"{doc_id}.md").write_text(md, encoding="utf-8")
    return md, info


def work_copy(path: Path, work: Path, doc_id: str) -> Path:
    """kordoc에는 원래 파일 이름 대신 문서번호 이름의 사본을 넘긴다(지시서 v2 16절).
    원래 이름에 든 특수 문자(&, |, % 등)를 cmd가 잘못 해석하는 문제와, 고인 이름이 든 파일 이름이
    명령줄에 남는 문제를 함께 막는다. 사본은 secure/work/ 안에 남는다."""
    dst = work / f"{doc_id}{path.suffix.lower()}"
    shutil.copy2(path, dst)
    return dst


def extract(path: Path, work: Path, doc_id: str, log: Path, fax_method: str = "B", det: str = "mobile",
            prep: str = "gray8", scan_engine: str = "kordoc", rotate_below: float = 0.8) -> tuple[str, str, dict]:
    st = source_type(path)
    work.mkdir(parents=True, exist_ok=True)
    if st in ("hwp", "hwpx", "pdf-text"):
        return st, run_kordoc(work_copy(path, work, doc_id), work / f"{doc_id}.md", False, log), {}
    if st == "pdf-ocr":
        if scan_engine == "kordoc":
            return st, run_kordoc(work_copy(path, work, doc_id), work / f"{doc_id}.md", True, log), {}
        # 비교용: 스캔 PDF를 이미지로 바꿔 팩스 절차로 읽는다
        import pymupdf as fitz
        with fitz.open(path) as d:
            pix = d[0].get_pixmap(dpi=200, colorspace=fitz.csGRAY)
            png = work / f"{doc_id}.page.png"
            pix.save(png)
        md, info = read_fax(png, work, doc_id, log, fax_method, det, prep, rotate_below)
        return st, md, info
    if st == "fax":
        md, info = read_fax(path, work, doc_id, log, fax_method, det, prep, rotate_below)
        return st, md, info
    raise ValueError("지원하지 않는 파일 형식")
