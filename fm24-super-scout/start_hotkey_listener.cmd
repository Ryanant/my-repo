@echo off
cd /d "%~dp0"
start "FM24 Super Scout hotkeys" /min pythonw.exe hotkey_listener.py
echo FM24 Super Scout hotkeys enabled: Ctrl+Alt+D or Ctrl+Shift+F9
timeout /t 3 /nobreak >nul
