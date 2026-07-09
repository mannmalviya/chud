"""Windows backend via PowerShell + user32.

Untested by the author (built on Linux). Uses SetWindowPos(HWND_TOPMOST) for real
always-on-top and SetForegroundWindow to swap focus. The work window is captured as
an HWND (GetForegroundWindow) at session start; the phone is found by window title
containing the phone-profile marker.
"""
from __future__ import annotations

import subprocess

from . import PHONE_MARKER

_USER32 = r"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class U {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
  [DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string name);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
  public delegate bool EnumProc(IntPtr h, IntPtr p);
}
"@
"""


def _ps(script: str) -> str:
    full = _USER32 + "\n" + script
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", full],
        capture_output=True, text=True,
    ).stdout.strip()


def capture_work() -> str | None:
    return _ps("[U]::GetForegroundWindow().ToInt64()") or None


def raise_work(handle: str) -> None:
    _ps(f"[U]::SetForegroundWindow([IntPtr]{handle})")


def raise_phone() -> None:
    # Find a top-level window whose title contains the phone marker, pin topmost, focus.
    _ps(
        r"""
$target=[IntPtr]::Zero
$sb=New-Object System.Text.StringBuilder 512
$cb=[U+EnumProc]{ param($h,$p)
  [void][U]::GetWindowText($h,$sb,512)
  if($sb.ToString() -like '*""" + PHONE_MARKER + r"""*'){ $script:target=$h; return $false }
  return $true
}
[void][U]::EnumWindows($cb,[IntPtr]::Zero)
if($target -ne [IntPtr]::Zero){
  [void][U]::SetWindowPos($target,[IntPtr]-1,0,0,0,0,0x0003)  # HWND_TOPMOST, NOMOVE|NOSIZE
  [void][U]::SetForegroundWindow($target)
}
"""
    )
