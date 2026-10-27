# 설치 안내 (Claude Code가 읽고 따라 하는 문서)

직원은 Claude Code에 **"INSTALL-ClaudeCode.md 대로 설치해 줘"** 라고 말하면 된다. 이 문서는 Claude Code가 단계마다 명령을 실행하고 결과를 확인하도록 쓴 것이다.

> **주의: 이 설치 순서는 아직 Windows PC에서 처음부터 끝까지 실행해 본 적이 없다.** 같은 코드는 맥에서 가짜 공문 26건으로 시험해 놓친 개인정보 0건을 확인했다. Windows에서 막히면 맨 아래 "막힐 때 확인할 곳"을 먼저 본다.

## Claude Code에게 — 진행 방식

- 아래 1~9단계를 순서대로 한다. 단계마다 "확인" 항목을 실제 명령 결과로 확인한 뒤 다음 단계로 간다. 확인하지 못한 것은 직원에게 "확인 안 됨"이라고 말한다.
- 명령은 PowerShell 기준이다. 관리자 권한이 필요한 단계(6단계 방화벽)는 직원에게 관리자 PowerShell을 열어 달라고 요청한다.
- 설치 위치는 `C:\nanum-mask` 하나로 고정한다. 코드의 기본 경로, 방화벽 규칙, 읽기 금지 규칙이 모두 이 경로를 쓴다. 경로에 띄어쓰기나 한글이 들어가면 kordoc 실행이 실패할 수 있다.
- **설치 중에는 실제 공문을 다루지 않는다.** 시험은 8단계의 가짜 공문으로만 한다. 설치가 끝나면 `C:\nanum-mask\CLAUDE.md`의 규칙을 따른다.
- 이 PC의 GPU(GTX 1050 Ti)는 쓰지 않는다. 모든 처리는 CPU로 한다. `paddlepaddle-gpu`나 CUDA를 설치하지 않는다.
- 같은 명령이 세 번 연속 실패하면 멈추고, 어떤 단계에서 어떤 오류가 났는지 직원에게 알린다. 오류 메시지는 그대로 보여 줘도 된다(설치 단계에는 공문이 없다).

## 1. 준비물: Git, Python, Node

이 프로그램은 PC에 이미 설치된 Python·Node와 따로, **가리기 전용 Python과 Node**를 `C:\nanum-mask` 안에 둔다. 6단계에서 이 두 프로그램만 인터넷을 막기 때문이다. PC에 있는 다른 Node를 막으면 Claude Code처럼 Node로 도는 프로그램도 인터넷을 쓰지 못한다.

1-1. 디스크 여유 공간이 4GB 이상인지 확인한다.

```powershell
Get-PSDrive C | Select-Object @{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}
```

1-2. Git이 없으면 설치한다. 설치 뒤에는 새 PowerShell 창을 열어야 `git`이 잡힌다.

```powershell
git --version
# 없으면
winget install --id Git.Git -e --source winget --accept-package-agreements --accept-source-agreements
```

1-3. 설치 파일을 받을 임시 폴더를 만들고 Python 3.11.9 설치 파일을 받는다. 3.11.9는 3.11 계열에서 Windows 설치 파일이 나온 마지막 버전이다.

```powershell
New-Item -ItemType Directory -Force C:\nanum-setup | Out-Null
Invoke-WebRequest https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe -OutFile C:\nanum-setup\python-3.11.9-amd64.exe
```

1-4. Node 22 LTS의 Windows용 압축 파일(zip)을 받는다. 정확한 파일 이름은 공식 체크섬 목록에서 찾고, 받은 뒤 SHA-256 값을 대조한다.

```powershell
$base = "https://nodejs.org/dist/latest-v22.x"
$sums = (Invoke-WebRequest "$base/SHASUMS256.txt").Content -split "`n"
$line = $sums | Where-Object { $_ -match "node-v22\.[0-9.]+-win-x64\.zip$" } | Select-Object -First 1
$hash, $name = $line -split "\s+"
Invoke-WebRequest "$base/$name" -OutFile "C:\nanum-setup\$name"
if ((Get-FileHash "C:\nanum-setup\$name" -Algorithm SHA256).Hash.ToLower() -eq $hash) { "Node zip 확인: $name" } else { "SHA-256 불일치 — 다시 받기" }
```

**확인**: `git --version`이 버전을 출력하고, `C:\nanum-setup`에 Python 설치 파일과 Node zip이 있다.

## 2. 저장소 받기와 전용 Python·Node 풀기

2-1. 저장소를 `C:\nanum-mask`에 받는다. 이 폴더가 이미 있으면 덮어쓰지 말고 직원에게 알린다.

```powershell
git clone https://github.com/picoco1145/nanum-obit-masking.git C:\nanum-mask
```

2-2. 전용 Python을 `C:\nanum-mask\python311`에 조용히 설치한다. 시스템 PATH와 파일 연결은 바꾸지 않는다.

```powershell
Start-Process C:\nanum-setup\python-3.11.9-amd64.exe -Wait -ArgumentList '/quiet','InstallAllUsers=0','TargetDir=C:\nanum-mask\python311','PrependPath=0','Include_launcher=0','AssociateFiles=0','Shortcuts=0','Include_test=0'
C:\nanum-mask\python311\python.exe --version
```

2-3. 전용 Node를 `C:\nanum-mask\node`에 푼다. zip 안의 폴더 하나를 `node`라는 이름으로 옮긴다.

```powershell
$zip = Get-ChildItem C:\nanum-setup\node-v22*-win-x64.zip | Select-Object -First 1
Expand-Archive $zip.FullName -DestinationPath C:\nanum-setup\node-unzip -Force
Move-Item (Get-ChildItem C:\nanum-setup\node-unzip -Directory | Select-Object -First 1).FullName C:\nanum-mask\node
C:\nanum-mask\node\node.exe --version
```

**확인**: Python은 `Python 3.11.9`, Node는 `v22.`로 시작하는 버전을 출력한다. `C:\nanum-mask\node\node.exe`가 있다.

## 3. 가상환경과 파이썬 패키지, 모델

3-1. 가상환경을 만들고 패키지를 설치한다. 버전은 `requirements.txt`에 맥에서 시험한 그대로 적혀 있다(PaddleOCR 3.4.1, paddlepaddle 3.3.1 CPU판, torch 2.14.1, transformers 5.20.2 등). 10~20분 걸릴 수 있다.

```powershell
cd C:\nanum-mask
C:\nanum-mask\python311\python.exe -m venv C:\nanum-mask\.venv
C:\nanum-mask\.venv\Scripts\python.exe -m pip install --upgrade pip
C:\nanum-mask\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

- 어떤 패키지가 그 버전으로 설치되지 않으면 가장 가까운 버전을 설치하고, 어떤 패키지를 몇 버전으로 바꿨는지 직원에게 알린다.

3-2. 모델을 받는다. 공문은 다루지 않고 모델 파일만 받는다.

```powershell
$env:PYTHONUTF8 = "1"
C:\nanum-mask\.venv\Scripts\python.exe tools\fetch_models.py
```

받는 모델은 다음과 같다.

| 용도 | 모델 | 위치 |
|---|---|---|
| 팩스 글자 위치 찾기 | `PP-OCRv5_mobile_det` | `models\paddlex\official_models\` |
| 팩스 한국어 글자 읽기 | `korean_PP-OCRv5_mobile_rec` (반드시 이 이름으로 지정) | 같은 곳 |
| 이름 찾기(NER, 문장에서 사람 이름을 찾는 모델) | `atonlee/koelectra-ko-pii-ner` | `models\ner\koelectra-ko-pii-ner\` |
| 스캔 PDF 글자 읽기(kordoc) | PP-OCRv5 korean ONNX | `kordoc\models\ppocr\` (4단계 뒤에 받는다) |

- 팩스 인식 설정은 코드(`app\extract.py`)에 들어 있다. 긴 변을 1600픽셀로 맞추고(`text_det_limit_type="max"`, `text_det_limit_side_len=1600`), CPU로 읽는다.
- 이 단계에서는 kordoc이 아직 없으므로 "3. kordoc 글자 인식 모델: 확인 못 함(kordoc 미설치)"이 나오는 것이 정상이다.

**확인**: `fetch_models.py` 출력에서 1번과 2번이 "있음"이다. 2번이 "시험한 파일과 다름"이면 8단계 자체 시험 결과를 특히 꼼꼼히 본다.

## 4. kordoc 설치와 NANUM_KORDOC 설정

kordoc은 HWP·HWPX·PDF 공문을 표 모양을 살린 글(마크다운)로 바꾸는 Node 프로그램이다. 전용 Node로 `C:\nanum-mask\kordoc`에 설치한다.

```powershell
$env:Path = "C:\nanum-mask\node;" + $env:Path
C:\nanum-mask\node\npm.cmd install --prefix C:\nanum-mask\kordoc kordoc@4.15.5
Test-Path C:\nanum-mask\kordoc\node_modules\kordoc\dist\cli.js
```

kordoc의 글자 인식 모델을 받고, 가리기 프로그램이 kordoc을 찾도록 환경 변수를 정한다. `app\kordoc-safe.cmd`는 kordoc을 오프라인 설정과 통신 감시 장치(`app\netguard.cjs`)를 켠 채로 실행하는 파일이다.

```powershell
C:\nanum-mask\.venv\Scripts\python.exe tools\fetch_models.py
[Environment]::SetEnvironmentVariable("NANUM_KORDOC", "C:\nanum-mask\app\kordoc-safe.cmd", "User")
$env:NANUM_KORDOC = "C:\nanum-mask\app\kordoc-safe.cmd"
cmd /c "C:\nanum-mask\app\kordoc-safe.cmd --version"
```

**확인**: `fetch_models.py`의 결과가 "모델 준비 완료"이고, 마지막 명령이 `4.15.5`를 출력한다.

## 5. 폴더 만들기

```powershell
cd C:\nanum-mask
"inbox","pending","masked","learn","logs","secure\originals","secure\maps","secure\review","secure\learn","secure\work" |
  ForEach-Object { New-Item -ItemType Directory -Force (Join-Path C:\nanum-mask $_) | Out-Null }
```

| 폴더 | 들어가는 것 | Claude가 읽어도 되는가 |
|---|---|---|
| `inbox\` | 받은 공문 원본을 직원이 넣는 곳 | 안 됨 |
| `pending\` | 가렸지만 검수 전인 사본 | 안 됨 |
| `masked\` | 검수를 마친 가린 사본 | **이 폴더만 읽는다** |
| `secure\` | 처리한 원본, 대조표(가린 표시와 원래 값의 짝), 검수 화면 자료, 검수 표시. **이 PC 밖으로 내보내지 않는다** | 안 됨 |
| `learn\` | 오답 노트 가운데 진짜 값이 없는 부분 | 읽어도 됨 |
| `logs\` | 처리 기록(건수와 상태만) | 읽어도 됨 |

- `C:\nanum-mask`를 구글 드라이브, OneDrive, NAS 동기화 폴더 안으로 옮기거나 연결하지 않는다. OneDrive가 "바탕화면·문서 폴더 백업"을 켜 두었더라도 `C:\nanum-mask`는 그 대상이 아니다.

**확인**: 위 10개 폴더가 모두 있다.

## 6. Windows 방화벽으로 바깥 연결 막기

모델을 모두 받은 뒤에 한다(3·4단계 확인을 마친 뒤). 직원에게 **관리자 PowerShell**을 열어 달라고 요청하고, 그 창에서 아래를 실행한다. 가상환경의 `python.exe`는 전용 Python을 다시 실행하는 실행기이므로 두 파일을 모두 막는다.

```powershell
New-NetFirewallRule -DisplayName "nanum-mask python 외부 차단" -Direction Outbound -Action Block -Program "C:\nanum-mask\python311\python.exe"
New-NetFirewallRule -DisplayName "nanum-mask venv 외부 차단"   -Direction Outbound -Action Block -Program "C:\nanum-mask\.venv\Scripts\python.exe"
New-NetFirewallRule -DisplayName "nanum-mask node 외부 차단"   -Direction Outbound -Action Block -Program "C:\nanum-mask\node\node.exe"
```

확인 명령(일반 PowerShell에서 실행해도 된다):

```powershell
C:\nanum-mask\.venv\Scripts\python.exe -c "import socket; socket.create_connection(('example.com', 443), 5); print('연결됨 - 차단 실패')"
C:\nanum-mask\node\node.exe -e "require('https').get('https://example.com',()=>console.log('연결됨 - 차단 실패')).on('error',e=>console.log('차단됨', e.code))"
```

**확인**: 파이썬 명령은 오류로 끝나고 "연결됨"을 출력하지 않는다. Node 명령은 "차단됨"을 출력한다.

- 나중에 모델을 다시 받거나 패키지를 설치해야 할 때만 `Disable-NetFirewallRule -DisplayName "nanum-mask*"`로 잠시 끄고, 끝나면 곧바로 `Enable-NetFirewallRule -DisplayName "nanum-mask*"`로 다시 켠다. 규칙을 끈 동안에는 공문을 처리하지 않는다.

## 7. Claude Code 읽기 금지 규칙

Claude Code가 원본 쪽 폴더를 열지 못하게 두 곳에 규칙을 넣는다.

7-1. 저장소에 들어 있는 `C:\nanum-mask\.claude\settings.json`에는 아래 규칙이 이미 있다. 이 규칙은 Claude Code를 `C:\nanum-mask`에서 시작했을 때 적용된다.

7-2. Claude Code를 다른 폴더에서 시작해도 적용되도록, 직원 계정의 사용자 설정 `%USERPROFILE%\.claude\settings.json`에도 같은 규칙을 **합쳐 넣는다.** 파일이 이미 있으면 다른 설정은 그대로 두고 `permissions.deny` 목록에 아래 여섯 줄만 더한다. 고치기 전에 원래 파일을 `settings.json.bak-날짜`로 복사해 둔다.

```json
{
  "permissions": {
    "deny": [
      "Read(//c/nanum-mask/inbox/**)",
      "Read(//c/nanum-mask/pending/**)",
      "Read(//c/nanum-mask/secure/**)",
      "Edit(//c/nanum-mask/inbox/**)",
      "Edit(//c/nanum-mask/pending/**)",
      "Edit(//c/nanum-mask/secure/**)"
    ]
  }
}
```

7-3. 이 규칙은 Bash·PowerShell 명령까지 완전히 막지는 못한다. 그래서 직원 계정의 `%USERPROFILE%\.claude\CLAUDE.md` 끝에 아래 문장을 더한다(파일이 없으면 만든다). 저장소의 `C:\nanum-mask\CLAUDE.md`에도 같은 문장이 있다.

```
## 공문 가리기 프로그램 (C:\nanum-mask)
- C:\nanum-mask\inbox, pending, secure 폴더의 파일 내용은 어떤 도구로도(Read, type, cat, Get-Content 포함) 열거나 출력하지 않는다.
- 공문 내용이 필요하면 C:\nanum-mask\masked\ 의 가린 사본만 읽는다.
- 정규식 수정안을 쓸 때는 C:\nanum-mask\learn\proposals\requests\ 의 가짜화한 요청만 읽는다.
```

**확인**: 두 settings.json이 올바른 JSON인지 확인한다(`Get-Content 파일 -Raw | ConvertFrom-Json`이 오류 없이 끝난다). 직원에게 Claude Code를 다시 시작해 달라고 하고, 새 세션에서 `C:\nanum-mask\secure\` 안의 아무 파일을 Read로 열려고 하면 거부되는지 확인한다(이때 secure에는 아직 공문이 없다).

## 8. 가짜 공문으로 자체 시험

가짜 공문 26건(텍스트 PDF 8, HWPX 2, 스캔 PDF 8, 팩스 이미지 8)을 만들어 가리고, 정답표와 대조해 채점한다. 가짜 공문의 이름·번호는 모두 지어낸 값이다. 글꼴은 `C:\Windows\Fonts\malgun.ttf`(맑은 고딕)를 자동으로 쓴다.

```powershell
cd C:\nanum-mask
$env:PYTHONUTF8 = "1"
C:\nanum-mask\.venv\Scripts\python.exe tests\selftest.py
```

이 명령은 정규식 단위 시험 → 가짜 공문 만들기 → 가리기 → 채점 → 화면·로그 점검을 차례로 한다. 맥에서는 2~3분 걸렸고, 이 PC에서는 더 걸릴 수 있다. 처음 한 번은 모델을 읽느라 첫 팩스가 특히 오래 걸린다.

**확인(합격 기준)**:
- 단위 시험이 `66 passed`이다.
- 채점 합계가 "놓침 0, 가리면 안 되는 값 가림 0, 누출 재검사 실패 0"이다.
- 화면·로그 점검이 "이상 없음"이다(`logs\netguard.log`가 비어 있거나 없다).
- 마지막 줄이 "결과: 합격"이다.

합격하면 회귀 기준(오답 노트가 새 규칙을 반영할 때 예전 성적이 나빠지지 않았는지 비교하는 기준)을 만든다. `selftest-날짜-시각` 폴더 이름은 위 출력의 마지막 줄에 있다.

```powershell
C:\nanum-mask\.venv\Scripts\python.exe app\learn.py init-base --from tests\out\selftest-날짜-시각 --fake tests\fake
```

맥 시험 결과와 비교해 직원에게 알린다. 맥에서는 놓침 0건이었고, 장당 처리 시간(CPU)은 텍스트 PDF 0.44초, HWPX 0.26초, 스캔 PDF 3.16초, 팩스 11.16초였다. 이 PC의 장당 시간은 `results\eval_selftest-…json`의 `cpu_median_s`·`wall_median_s`에 있다(Windows에서는 CPU 시간 측정 모듈이 없어 `cpu_median_s`가 0으로 나올 수 있으므로 `wall_median_s`를 본다).

## 9. 바탕화면 아이콘 만들기

```powershell
powershell -ExecutionPolicy Bypass -File C:\nanum-mask\windows\make-shortcut.ps1
```

바탕화면에 아이콘 두 개가 생긴다.

- **공문 가리기**: `inbox`의 공문을 모두 가린 뒤 검수 화면(http://127.0.0.1:8765)을 연다. 검수를 마치면 검은 창을 닫는다.
- **받은 공문 넣는 곳**: `inbox` 폴더를 연다.

**확인**: 아이콘 두 개가 바탕화면에 있다. `inbox`가 비어 있는 상태에서 "공문 가리기"를 실행하면 "처리할 공문 0건"이 나오고 검수 화면이 브라우저에 열린다.

마지막으로 직원에게 설치 결과를 한 번에 알린다: 단계별 확인 결과, 바꾼 패키지 버전, 자체 시험 합격 여부와 장당 처리 시간, 남은 할 일(아래).

## 설치 뒤 단체가 정할 것

`C:\nanum-mask\config\policy.yaml`에 적는다. 정하기 전에는 안전한 쪽(가림, 지우지 않음)이 기본값이다.

- 담당 공무원 이름과 기관 대표전화·팩스·기관 주소를 가릴지(`mask_officials`, `mask_org_contact`, 기본 가림)
- 원본과 대조표를 보관할지, 몇 일 보관할지(`keep_originals`, `retention_days`, 기본 보관·지우지 않음)
- 첫 주는 모든 문서를 사람이 검수한다(`review_mode: all`). 이후 표시된 문서만 검수할지는 첫 주 결과를 보고 정한다.
- 팩스를 180도 돌려 다시 읽는 기준(`fax_rotate_below`, 기본 0.8)은 실제 팩스 몇 장을 처리해 본 뒤 다시 정한다.

## 막힐 때 확인할 곳

| 증상 | 확인할 것 |
|---|---|
| `pip install`에서 paddlepaddle 3.3.1을 찾지 못한다 | Python이 3.11 64비트인지 확인한다. 그래도 없으면 PaddlePaddle 공식 CPU 저장소를 쓴다: `pip install paddlepaddle==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/` |
| torch 설치가 매우 크거나 CUDA판을 받으려 한다 | CPU판을 지정한다: `pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu` |
| `import paddle`에서 DLL 오류가 난다 | "Microsoft Visual C++ 재배포 가능 패키지(x64)"를 설치한다: `winget install Microsoft.VCRedist.2015+.x64` |
| 팩스 처리에서 PaddleOCR이 모델을 찾지 못한다 | `models\paddlex\official_models\` 아래 두 모델 폴더가 있는지 본다. 없으면 방화벽 규칙을 잠시 끄고 `tools\fetch_models.py`를 다시 실행한다 |
| 팩스 한 장이 1분 넘게 걸린다 | 다른 무거운 프로그램을 닫는다. 그래도 느리면 `app\extract.py`의 `text_det_limit_side_len` 값을 1280으로 낮춰 자체 시험을 다시 돌리고 놓침이 0인지 확인한다 |
| `kordoc 실패(exit 9009)` 또는 `exit 1` | `C:\nanum-mask\node\node.exe`와 `C:\nanum-mask\kordoc\node_modules\kordoc\dist\cli.js`가 있는지, `NANUM_KORDOC`이 `C:\nanum-mask\app\kordoc-safe.cmd`인지 본다. 새 PowerShell 창에서 환경 변수를 다시 읽는다 |
| 스캔 PDF만 실패한다 | `tools\fetch_models.py --check`에서 3번(kordoc 모델)이 "있음"인지 본다 |
| 가짜 HWPX가 만들어지지 않는다 | `kordoc-safe.cmd generate --help`가 동작하는지 본다. 나머지 24건으로 시험은 계속할 수 있다 |
| 한글이 깨져 보인다 | 같은 창에서 `$env:PYTHONUTF8="1"`, `chcp 65001`을 실행한 뒤 다시 시도한다 |
| 검수 화면이 열리지 않는다 | 다른 프로그램이 8765번 포트를 쓰는지 본다. `app\mask.py review --port 8766`으로 바꿔 연다 |
| 방화벽 확인에서 "연결됨"이 나온다 | 규칙의 프로그램 경로가 실제 파일 경로와 같은지 `Get-NetFirewallRule -DisplayName "nanum-mask*" | Get-NetFirewallApplicationFilter`로 본다 |
| 자체 시험에서 놓침이 0이 아니다 | 공문 처리를 시작하지 않는다. `results\eval_selftest-…json`의 형식별 놓침 건수와 OCR 손실 건수만 직원에게 알리고, 어떤 형식에서 놓쳤는지 함께 살핀다. 가짜 값이므로 내용을 봐도 되지만 실제 공문 폴더는 열지 않는다 |
