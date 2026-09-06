@echo off
cd /d "%~dp0"
if "%~1"=="" (
  python memory_dump.py
) else (
  python memory_dump.py --game-date "%~1"
)
if errorlevel 1 (
  echo Memory dump failed.
  pause
) else (
  echo Memory dump completed successfully.
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$server = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue; if ($server) { Stop-Process -Id $server[0].OwningProcess -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 500 }; Start-Process -FilePath 'python' -ArgumentList 'app.py' -WorkingDirectory '%~dp0' -WindowStyle Hidden; Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8765'"
)
