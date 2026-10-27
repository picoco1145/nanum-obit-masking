@echo off
rem kordoc offline wrapper for Windows. Set the NANUM_KORDOC environment variable to the full path of this file.
rem netguard.cjs blocks network calls inside the Node process. The Windows Firewall rules block it at the OS level.
rem Paths are relative to this file: <root>\app\kordoc-safe.cmd, <root>\node\node.exe, <root>\kordoc\node_modules\kordoc.
rem Keep <root> free of spaces (C:\nanum-mask is recommended) because NODE_OPTIONS does not accept quoted paths reliably.
setlocal
for %%I in ("%~dp0..") do set "NANUM_ROOT=%%~fI"
set "KORDOC_OFFLINE=1"
set "KORDOC_MODEL_CACHE=%NANUM_ROOT%\kordoc\models"
if "%KORDOC_NETGUARD_LOG%"=="" set "KORDOC_NETGUARD_LOG=%NANUM_ROOT%\logs\netguard.log"
set "NODE_OPTIONS=--require %NANUM_ROOT%\app\netguard.cjs"
"%NANUM_ROOT%\node\node.exe" "%NANUM_ROOT%\kordoc\node_modules\kordoc\dist\cli.js" %*
exit /b %ERRORLEVEL%
