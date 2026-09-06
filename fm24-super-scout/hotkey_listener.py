"""Windows-only global hotkey launcher for the FM24 read-only dump."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import subprocess
from pathlib import Path

USER32 = ctypes.windll.user32
MOD_ALT, MOD_CONTROL, MOD_SHIFT = 0x0001, 0x0002, 0x0004
WM_HOTKEY = 0x0312
VK_F9 = 0x78
LAUNCHER = Path(__file__).with_name("dump_latest.cmd")


def main() -> None:
    # Support both the originally documented shortcut and the fallback key.
    if not USER32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT, ord("D")):
        raise SystemExit("Could not register Ctrl+Alt+D; it is already in use.")
    if not USER32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_SHIFT, VK_F9):
        USER32.UnregisterHotKey(None, 1)
        raise SystemExit("Could not register Ctrl+Shift+F9; it is already in use.")
    try:
        message = ctypes.wintypes.MSG()
        while USER32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            if message.message == WM_HOTKEY and message.wParam in (1, 2):
                subprocess.Popen(["cmd.exe", "/c", str(LAUNCHER)], cwd=str(LAUNCHER.parent))
            USER32.TranslateMessage(ctypes.byref(message))
            USER32.DispatchMessageW(ctypes.byref(message))
    finally:
        USER32.UnregisterHotKey(None, 1)
        USER32.UnregisterHotKey(None, 2)


if __name__ == "__main__":
    main()
