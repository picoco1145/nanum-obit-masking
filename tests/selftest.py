"""가짜 공문으로 하는 자체 시험 (지시서 v2 15절의 합격 기준 가운데 자동으로 확인할 수 있는 것).

  python tests/selftest.py                 # 가짜 공문 26건 전체(맥 기준 약 2~3분, 처음 한 번은 견본 생성 포함)
  python tests/selftest.py --only _text    # 텍스트 PDF만 빠르게

순서: 정규식 단위 시험 → 가짜 공문 만들기(없을 때만) → 가리기 실행 → 채점 → 화면·로그 점검.
화면에는 건수만 나온다. 결과 폴더는 tests/out/selftest-<시각>/ 이고 덮어쓰지 않는다.
합격 기준: 놓침 0, 가리면 안 되는 값 가림 0, 누출 재검사 실패 0, netguard.log 비어 있음, 화면·로그에 가짜 값 없음.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def step(title: str, cmd: list[str], log: Path | None = None) -> subprocess.CompletedProcess:
    print(f"\n### {title}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if log is not None:
        log.write_text(r.stdout + r.stderr, encoding="utf-8")
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="파일 이름에 들어간 낱말로 거르기(예: _text, _fax)")
    a = ap.parse_args()
    ok = True

    r = step("1. 정규식 단위 시험", [PY, "-m", "pytest", "-q", "tests/test_rules.py"])
    last = (r.stdout.strip().splitlines() or ["(출력 없음)"])[-1]
    print(last)
    ok &= r.returncode == 0

    if not (ROOT / "tests/fake/answers").exists():
        r = step("2. 가짜 공문 만들기", [PY, "tests/make_fake.py"])
        n = len(list((ROOT / "tests/fake/answers").glob("*.answer.json"))) if (ROOT / "tests/fake/answers").exists() else 0
        print(f"정답표 {n}개, 종료 코드 {r.returncode}")
        if r.returncode != 0 or n == 0:
            print("가짜 공문을 만들지 못했습니다. 글꼴(FAKE_FONT)과 kordoc(NANUM_KORDOC) 설정을 확인하세요.")
            return 1
        if "hwpx 생성 실패" in r.stderr:
            print("주의: HWPX 견본 생성에 실패했습니다(kordoc generate). 나머지 형식으로 계속합니다.")
    else:
        print("\n### 2. 가짜 공문: 이미 있음(tests/fake/)")

    name = "selftest-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "tests/out" / name
    out.mkdir(parents=True, exist_ok=True)
    cmd = [PY, "app/mask.py", "run", "--inbox", "tests/fake", "--out", str(out)]
    if a.only:
        cmd += ["--only", a.only]
    run_log = out / "run.log"
    r = step("3. 가리기 실행", cmd, run_log)
    done = sum(1 for ln in r.stdout.splitlines() if " 상태 " in ln)
    failed_read = sum(1 for ln in r.stdout.splitlines() if "읽기 실패" in ln)
    print(f"처리 {done}건, 읽기 실패 {failed_read}건, 종료 코드 {r.returncode}")
    ok &= r.returncode == 0 and failed_read == 0 and done > 0

    r = step("4. 채점", [PY, "tests/evaluate.py", str(out), "--name", name])
    print(r.stdout.strip())
    res = ROOT / "results" / f"eval_{name}.json"
    if res.exists():
        summ = json.loads(res.read_text(encoding="utf-8"))["summary"]
        leak = sum(s["leak_total"] for s in summ.values())
        must_not = sum(s["over_must_not"] for s in summ.values())
        recheck = sum(s["recheck_fail"] for s in summ.values())
        print(f"합계: 놓침 {leak}, 가리면 안 되는 값 가림 {must_not}, 누출 재검사 실패 {recheck}")
        ok &= leak == 0 and must_not == 0 and recheck == 0
    else:
        print("채점 결과 파일이 없습니다.")
        ok = False

    r = step("5. 화면·로그 점검", [PY, "tests/check_logs.py", str(run_log), str(out)])
    print(r.stdout.strip())
    ok &= "이상 없음" in r.stdout

    print("\n결과:", "합격" if ok else "불합격 — 위 항목을 확인하세요", f"(결과 폴더 tests/out/{name})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
