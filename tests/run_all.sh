#!/bin/bash
# 모든 비교 실행. 결과는 tests/out/<이름>/ 과 results/eval_<이름>.json
cd "$(dirname "$0")/.."
PY=.venv/bin/python
run() { name=$1; shift; echo "### $name"; $PY app/mask.py run --inbox tests/fake --out tests/out/$name "$@" 2>&1 | grep -E "^2026|실패"; $PY tests/evaluate.py tests/out/$name; }
run spec_ner     --profile spec
run spec_noner   --profile spec  --no-ner
run fixed_ner    --profile fixed
run fixed_noner  --profile fixed --no-ner
run fixed_faxB   --profile fixed --only _fax --fax-method B
run fixed_faxA_none --profile fixed --only _fax --fax-method A --prep none
