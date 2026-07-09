"""macOS backend via AppleScript (osascript).

Untested by the author (built on Linux). True always-on-top of another app's window
isn't supported by the public APIs, so we approximate: raise/activate the target app.
Requires a one-time Accessibility permission grant for the controlling terminal/app.

The phone is a Chrome window opened with a dedicated profile; we identify "the work
window" by the process id captured at session start.
"""
from __future__ import annotations

import subprocess


def _osa(script: str) -> str:
    return subprocess.run(["osascript", "-e", script],
                          capture_output=True, text=True).stdout.strip()


def capture_work() -> str | None:
    # Bundle id of the frontmost app when the agent starts.
    bid = _osa(
        'tell application "System Events" to get bundle identifier of first process whose frontmost is true'
    )
    return bid or None


def raise_work(handle: str) -> None:
    # handle is a bundle identifier.
    _osa(f'tell application id "{handle}" to activate')


def raise_phone() -> None:
    # Bring Google Chrome forward. With a single dedicated phone window this is the
    # visible one; approximate "always on top" by re-raising on each swap.
    _osa('tell application "Google Chrome" to activate')
