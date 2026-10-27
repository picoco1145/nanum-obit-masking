# 부고 공문 개인정보 가리기 — Claude Code 작업 규칙

이 폴더(`C:\nanum-mask\`)는 받은 공문의 개인정보를 이 PC 안에서 가린 뒤, 가린 사본만 Claude가 읽도록 만든 프로그램이다. 설계 문서는 `docs\부고공문-마스킹설계-ClaudeCode-v2.md`, 설치 순서는 `INSTALL-ClaudeCode.md`에 있다.

## 반드시 지킬 것

- C:\nanum-mask\inbox, pending, secure 폴더의 파일 내용은 어떤 도구로도(Read, type, cat, Get-Content 포함) 열거나 출력하지 않는다.
- 공문 내용이 필요하면 C:\nanum-mask\masked\ 의 가린 사본만 읽는다.
- 정규식 수정안을 쓸 때는 C:\nanum-mask\learn\proposals\requests\ 의 가짜화한 요청만 읽는다.
- inbox, pending, secure 폴더는 파일 이름과 개수만 확인할 수 있다. 파일 이름에 고인 이름이 들어 있을 수 있으므로 이름 목록도 대화에 옮겨 적지 않고 개수만 말한다.
- `app\` 코드에 네트워크 모듈(`requests`, `httpx`, `urllib.request`, `anthropic`, `openai` 등)을 넣지 않는다. 프로그램은 화면과 로그에 값을 쓰지 않고 건수와 상태만 쓴다. 코드를 고칠 때도 이 규칙을 지킨다.
- `app\learn.py words`는 승인을 기다리는 낱말을 그대로 출력하므로 Claude가 실행하지 않는다. 직원은 검수 화면의 승인 화면(/proposals)에서 확인한다.
- 실제 공문으로 시험하지 않는다. 시험은 `tests\make_fake.py`가 만든 가짜 공문으로만 한다.
- 원본, 대조표, 검수 표시(`secure\`)를 지우거나 PC 밖(메일, 클라우드, 메신저)으로 옮기지 않는다. 보관 기간은 `config\policy.yaml`의 단체 결정을 따른다.

## 자주 쓰는 명령 (C:\nanum-mask 에서 실행)

| 하는 일 | 명령 |
|---|---|
| inbox의 공문 가리기 | `.venv\Scripts\python.exe app\mask.py run` |
| 검수 화면 열기 | `.venv\Scripts\python.exe app\mask.py review` 뒤 http://127.0.0.1:8765 |
| 한 건 승인(화면 대신) | `.venv\Scripts\python.exe app\mask.py approve 문서번호` |
| 오답 노트 반영 | `.venv\Scripts\python.exe app\learn.py ingest` |
| 수정안 검사·승인 | `app\learn.py check 수정안ID`, 직원이 승인하면 `app\learn.py approve 수정안ID` |
| 주간 보고 | `.venv\Scripts\python.exe app\learn.py report --days 7` |
| 자체 시험 | `.venv\Scripts\python.exe tests\selftest.py` |

## 정규식 수정안을 쓸 때

`learn\proposals\requests\`의 요청(가짜화한 값)만 보고 `learn\proposals\drafts\`에 수정안을 쓴다. 쓴 뒤 `learn.py check`로 회귀 시험을 돌리고, 통과하면 직원에게 승인 여부를 묻는다. 승인 명령은 직원이 허락한 뒤에만 실행한다.
