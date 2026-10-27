"""설치할 때 한 번만 실행하는 모델 내려받기 (인터넷 연결이 필요하다).

  python tools/fetch_models.py            # 세 가지 모델을 모두 받는다
  python tools/fetch_models.py --check    # 받지 않고 있는지만 확인한다

받는 모델
  1. PaddleOCR 팩스 글자 인식: PP-OCRv5_mobile_det(글자 위치 찾기) + korean_PP-OCRv5_mobile_rec(한국어 글자 읽기)
     → models/paddlex/official_models/  (약 18MB)
  2. 이름 찾기 모델(NER): atonlee/koelectra-ko-pii-ner (Apache-2.0)
     → models/ner/koelectra-ko-pii-ner/  (약 55MB)
  3. kordoc 스캔 PDF 글자 인식(PP-OCRv5 korean ONNX)
     → kordoc/models/ppocr/  (약 18MB, node와 kordoc을 먼저 설치해야 한다)

이 스크립트는 공문을 읽지 않는다. 모델을 받은 뒤에는 가리기 프로그램(mask.py)이
인터넷 연결을 막은 채로 이 폴더의 모델만 쓴다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDX = ROOT / "models/paddlex"
NER_DIR = ROOT / "models/ner/koelectra-ko-pii-ner"
NER_REPO = "atonlee/koelectra-ko-pii-ner"
NER_FILES = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json", "README.md"]
# 시제품에서 시험한 파일의 SHA-256. 다르면 모델이 바뀐 것이므로 자체 시험을 다시 확인한다.
NER_SHA256 = "e3ed229e2bc4299c98624f0a5bfc9c15e2d9942295dc2eba8a67105e628e92dc"
PADDLE_MODELS = ["PP-OCRv5_mobile_det", "korean_PP-OCRv5_mobile_rec"]
NODE = ROOT / ("node/node.exe" if os.name == "nt" else "node/bin/node")
KORDOC_CLI = ROOT / "kordoc/node_modules/kordoc/dist/cli.js"
KORDOC_MODELS = ROOT / "kordoc/models"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def paddle_ok() -> bool:
    return all((PDX / "official_models" / m / "inference.pdiparams").exists() for m in PADDLE_MODELS)


def ner_ok() -> bool:
    return all((NER_DIR / f).exists() for f in NER_FILES[:4])


def node_bin() -> str | None:
    if NODE.exists():
        return str(NODE)
    from shutil import which
    return which("node")


def kordoc_status() -> bool | None:
    nb = node_bin()
    if not nb or not KORDOC_CLI.exists():
        return None
    env = dict(os.environ, KORDOC_MODEL_CACHE=str(KORDOC_MODELS))
    r = subprocess.run([nb, str(KORDOC_CLI), "models", "--status"], env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        groups = json.loads(r.stdout)
    except ValueError:
        return False
    return any(g.get("group") == "ppocr" and g.get("allReady") for g in groups)


def fetch_paddle() -> None:
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(PDX)
    from paddleocr import PaddleOCR
    PaddleOCR(text_detection_model_name=PADDLE_MODELS[0], text_recognition_model_name=PADDLE_MODELS[1],
              use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)


def fetch_ner() -> None:
    from huggingface_hub import hf_hub_download
    NER_DIR.mkdir(parents=True, exist_ok=True)
    for f in NER_FILES:
        hf_hub_download(NER_REPO, f, local_dir=str(NER_DIR))


def fetch_kordoc() -> None:
    nb = node_bin()
    if not nb or not KORDOC_CLI.exists():
        print("  kordoc이 아직 없습니다. 설치 안내 4단계(kordoc 설치)를 마친 뒤 다시 실행하세요.")
        return
    from PIL import Image, ImageDraw
    with tempfile.TemporaryDirectory() as td:
        img = Path(td) / "model-check.png"
        im = Image.new("RGB", (640, 160), "white")
        ImageDraw.Draw(im).text((20, 60), "MODEL CHECK 2026 0123", fill="black")
        im.save(img)
        env = dict(os.environ, KORDOC_MODEL_CACHE=str(KORDOC_MODELS))
        env.pop("KORDOC_OFFLINE", None)
        r = subprocess.run([nb, str(KORDOC_CLI), str(img), "--silent", "-o", str(Path(td) / "out.md")],
                           env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"  kordoc 시험 실행 종료 코드 {r.returncode}")


def report() -> bool:
    p, n, k = paddle_ok(), ner_ok(), kordoc_status()
    print(f"1. PaddleOCR 모델(models/paddlex): {'있음' if p else '없음'}")
    if n:
        same = sha256(NER_DIR / "model.safetensors") == NER_SHA256
        print(f"2. 이름 찾기 모델(models/ner): 있음, 시험한 파일과 {'같음' if same else '다름 — 자체 시험으로 다시 확인하세요'}")
    else:
        print("2. 이름 찾기 모델(models/ner): 없음")
    print("3. kordoc 글자 인식 모델(kordoc/models): "
          + {True: "있음", False: "없음", None: "확인 못 함(kordoc 미설치)"}[k])
    return p and n and k is True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="받지 않고 상태만 확인")
    a = ap.parse_args()
    if not a.check:
        if not paddle_ok():
            print("PaddleOCR 모델을 받습니다…", flush=True)
            fetch_paddle()
        if not ner_ok():
            print("이름 찾기 모델을 받습니다…", flush=True)
            fetch_ner()
        if kordoc_status() is not True:
            print("kordoc 글자 인식 모델을 받습니다…", flush=True)
            fetch_kordoc()
    print()
    ok = report()
    print("\n결과:", "모델 준비 완료" if ok else "빠진 모델이 있습니다")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
