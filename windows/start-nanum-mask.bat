@echo off
rem Desktop launcher: masks every file in inbox, then opens the review screen (http://127.0.0.1:8765).
rem Close this window (or press Ctrl+C) when review is finished.
setlocal
for %%I in ("%~dp0..") do set "NANUM_ROOT=%%~fI"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if "%NANUM_KORDOC%"=="" set "NANUM_KORDOC=%NANUM_ROOT%\app\kordoc-safe.cmd"
cd /d "%NANUM_ROOT%"
echo.
echo [1/2] inbox ...
"%NANUM_ROOT%\.venv\Scripts\python.exe" app\mask.py run
echo.
echo [2/2] review screen: http://127.0.0.1:8765/
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:8765/'"
"%NANUM_ROOT%\.venv\Scripts\python.exe" app\mask.py review
pause
