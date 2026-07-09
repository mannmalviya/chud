"""OS + session detection, and the Wayland guard.

The whole window-control layer only works where one process can pin/focus another
window: Windows, macOS, and Linux/X11. Wayland compositors forbid it, so we detect
Wayland and refuse with a clear message rather than failing mysteriously later.
"""
from __future__ import annotations

import os
import shutil
import sys


def os_name() -> str:
    if sys.platform.startswith("linux"):
        return "linux"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform in ("win32", "cygwin"):
        return "windows"
    return "unknown"


def is_wayland() -> bool:
    if os_name() != "linux":
        return False
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def chrome_binary() -> str | None:
    candidates = [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "chrome",
    ]
    if os_name() == "macos":
        mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(mac):
            return mac
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found
    return None


def window_tool_status() -> tuple[bool, str]:
    """Return (ok, human message) for the OS-specific window tool."""
    name = os_name()
    if name == "linux":
        missing = [t for t in ("wmctrl", "xdotool") if not shutil.which(t)]
        if missing:
            return False, f"missing: {', '.join(missing)} (install: sudo apt install {' '.join(missing)})"
        return True, "wmctrl + xdotool present"
    if name == "macos":
        # AppleScript is always present; Accessibility permission is checked at runtime.
        return True, "osascript present (grant Accessibility permission on first use)"
    if name == "windows":
        return True, "PowerShell user32 backend"
    return False, "unsupported OS"


def supported() -> tuple[bool, str]:
    """Overall go/no-go for this machine."""
    name = os_name()
    if name == "unknown":
        return False, f"unsupported platform: {sys.platform}"
    if is_wayland():
        return (
            False,
            "Wayland detected. Foreign-window control is blocked by the compositor.\n"
            "Log out and choose an 'Xorg' / 'X11' session at the login screen, then retry.",
        )
    return True, name
