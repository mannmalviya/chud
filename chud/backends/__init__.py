"""Window-control backend, selected per OS. One interface:

    capture_work() -> handle | None      # the window the agent was launched in
    raise_work(handle)                   # focus that window
    raise_phone()                        # pin the phone on top and focus it

The phone Chrome window is tagged with a stable marker (WM_CLASS on X11) so we can
find it again regardless of the page title.
"""
from __future__ import annotations

from ..platform import os_name

# Stable identity for the phone window (also passed to Chrome via --class on Linux).
PHONE_MARKER = "chud"


def _impl():
    name = os_name()
    if name == "linux":
        from . import x11 as m
    elif name == "macos":
        from . import macos as m
    elif name == "windows":
        from . import win as m
    else:
        raise RuntimeError(f"no window backend for {name}")
    return m


def capture_work():
    return _impl().capture_work()


def raise_work(handle):
    if handle:
        _impl().raise_work(handle)


def raise_phone():
    _impl().raise_phone()


def phone_exists():
    """True/False where detectable (X11), None where not (macOS/Windows)."""
    fn = getattr(_impl(), "phone_exists", None)
    return fn() if fn else None


def phone_focused():
    """True when the phone window currently holds focus — i.e. the user is
    actively using it. False where the backend can't tell."""
    fn = getattr(_impl(), "phone_focused", None)
    return fn() if fn else False


def user_idle_ms():
    """Milliseconds since the user's last input, or None where undetectable."""
    fn = getattr(_impl(), "user_idle_ms", None)
    return fn() if fn else None


def phone_hidden():
    """True when the phone is minimized/absent. False where not detectable, so
    hidden-gated raises stay quiet rather than firing after every tool."""
    fn = getattr(_impl(), "phone_hidden", None)
    return fn() if fn else False


def minimize_phone():
    """Minimize the phone window (no-op where the backend can't)."""
    fn = getattr(_impl(), "minimize_phone", None)
    if fn:
        fn()


def watch_focus(profile_dir, on_user_hide=None):
    """Minimize the phone whenever focus moves off it (no-op where the backend
    can't watch focus). Meant to run as a detached helper process; calls
    on_user_hide each time the user (not chud) hides the phone."""
    fn = getattr(_impl(), "watch_focus", None)
    if fn:
        fn(profile_dir, on_user_hide)


def pause_phone_media(profile_dir):
    """Pause media playing in the phone (no-op where the backend can't)."""
    fn = getattr(_impl(), "pause_phone_media", None)
    if fn:
        fn(profile_dir)
