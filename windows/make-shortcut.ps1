# 바탕화면에 "공문 가리기" 아이콘(바로 가기)을 만든다. 저장소 폴더의 windows\ 안에서 실행한다.
#   powershell -ExecutionPolicy Bypass -File windows\make-shortcut.ps1
$root = Split-Path -Parent $PSScriptRoot
$desk = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut((Join-Path $desk '공문 가리기.lnk'))
$lnk.TargetPath = Join-Path $root 'windows\start-nanum-mask.bat'
$lnk.WorkingDirectory = $root
$lnk.IconLocation = "$env:SystemRoot\System32\shell32.dll,47"
$lnk.Description = '받은 공문의 개인정보를 가리고 검수 화면을 엽니다'
$lnk.Save()
$lnk2 = $ws.CreateShortcut((Join-Path $desk '받은 공문 넣는 곳.lnk'))
$lnk2.TargetPath = Join-Path $root 'inbox'
$lnk2.Save()
Write-Output "바탕화면 아이콘 2개를 만들었습니다: $desk"
