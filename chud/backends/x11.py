"""Linux/X11 backend using wmctrl + xdotool.

The phone window is launched by the launcher with `--class=chud`, so its
WM_CLASS is stable and we find it by class rather than by (mutating) title.

All shell-outs tolerate a missing tool (returns empty / no-op) so a hook never dies
just because wmctrl/xdotool isn't installed yet.
"""
from __future__ import annotations

import re
import subprocess

from . import PHONE_MARKER

# Cap every shell-out so a wedged X call can never hang an agent hook.
_TIMEOUT = 5


def _out(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=_TIMEOUT).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _do(cmd: list[str], timeout: float = _TIMEOUT) -> None:
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def capture_work() -> str | None:
    """The currently-active window id (the terminal or editor running the agent)."""
    return _out(["xdotool", "getactivewindow"]) or None


def _activate(wid: str) -> None:
    """Make a window visible instantly, then focus it. Map + raise first — the WM
    can't veto those — because GNOME/mutter's focus-stealing prevention makes
    `windowactivate --sync` stall (not fail) when it denies the focus switch, so
    it gets a short leash and XSetInputFocus is the fallback."""
    _do(["xdotool", "windowmap", wid])  # deiconify
    _do(["xdotool", "windowraise", wid])
    _do(["xdotool", "windowactivate", "--sync", wid], timeout=1)
    if _out(["xdotool", "getactivewindow"]) != wid:
        _do(["xdotool", "windowfocus", wid])


def raise_work(handle: str) -> None:
    _activate(handle)


def _area(wid: str) -> int:
    # `--shell` prints WIDTH=… HEIGHT=… lines we can eval-parse.
    vals = {}
    for line in _out(["xdotool", "getwindowgeometry", "--shell", wid]).splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            vals[k] = v
    try:
        return int(vals.get("WIDTH", 0)) * int(vals.get("HEIGHT", 0))
    except ValueError:
        return 0


def _phone_window_ids() -> list[str]:
    ids = _out(["xdotool", "search", "--class", PHONE_MARKER]).splitlines()
    return [i for i in ids if i.strip()]


def _phone_window_id() -> str | None:
    # Chrome --app registers several X windows sharing our class (including a tiny
    # 10x10 helper). Pick the largest-area one — the visible phone frame.
    ids = _phone_window_ids()
    if not ids:
        return None
    return max(ids, key=_area)


def phone_exists() -> bool:
    return _phone_window_id() is not None


def phone_focused() -> bool:
    active = _out(["xdotool", "getactivewindow"])
    return bool(active) and active in _phone_window_ids()


def user_idle_ms() -> int | None:
    """Milliseconds since the user's last keyboard/mouse input, or None when
    undetectable. Prefers xprintidle; falls back to GNOME mutter's idle
    monitor, which needs no extra package on GNOME desktops."""
    out = _out(["xprintidle"])
    if out.isdigit():
        return int(out)
    out = _out(["dbus-send", "--session", "--print-reply",
                "--dest=org.gnome.Mutter.IdleMonitor",
                "/org/gnome/Mutter/IdleMonitor/Core",
                "org.gnome.Mutter.IdleMonitor.GetIdletime"])
    m = re.search(r"uint64 (\d+)", out)
    return int(m.group(1)) if m else None


def phone_hidden() -> bool:
    """True when the phone is minimized or gone — i.e. worth raising again."""
    wid = _phone_window_id()
    if not wid:
        return True
    return "Iconic" in _out(["xprop", "-id", wid, "WM_STATE"])


def raise_phone() -> None:
    wid = _phone_window_id()
    if not wid:
        return
    # Pin above everything, then focus.
    _do(["wmctrl", "-i", "-r", wid, "-b", "add,above"])
    _activate(wid)


def minimize_phone() -> None:
    wid = _phone_window_id()
    if wid:
        _do(["xdotool", "windowminimize", wid])


def watch_focus(profile_dir: str, on_user_hide=None) -> None:
    """Hide the phone whenever the user focuses a non-phone window.

    Spawned as a detached process when the phone is raised, and lives for the
    phone window's lifetime. Reads _NET_ACTIVE_WINDOW change events from
    `xprop -spy` (event-driven — it sleeps between focus switches). Arms
    whenever the phone holds focus (a raise, or the user restoring it from the
    taskbar) and hides it on the next switch to another window; requiring the
    phone to hold focus first also keeps the raise's own focus churn from
    hiding the phone the moment it appears.

    on_user_hide fires only when *we* hide the phone here — i.e. the user
    clicked away from a visible phone. If the phone is already minimized when
    focus moves (chud's own `work` command did it), it is not a user gesture.
    """
    try:
        proc = subprocess.Popen(["xprop", "-root", "-spy", "_NET_ACTIVE_WINDOW"],
                                stdout=subprocess.PIPE, text=True)
    except FileNotFoundError:
        return
    try:
        armed = False
        for line in proc.stdout:
            m = re.search(r"window id # (0x[0-9a-fA-F]+)", line)
            if not m:
                continue
            active = str(int(m.group(1), 16))
            phones = _phone_window_ids()
            if not phones:
                return  # phone closed — the watcher's job is done
            if active in phones:
                armed = True
            elif armed and active != "0":  # 0x0 = no active window; not a click
                armed = False
                if phone_hidden():
                    continue  # chud minimized it, not the user
                pause_phone_media(profile_dir)
                minimize_phone()
                if on_user_hide:
                    on_user_hide()
    finally:
        proc.kill()


def pause_phone_media(profile_dir: str) -> None:
    """Pause whatever is playing in the phone (YouTube, TikTok, reels, …).

    Chrome exposes a per-process MPRIS player named
    org.mpris.MediaPlayer2.chromium.instance<pid>. We match the pid against the
    phone's dedicated profile so the user's main browser is never touched.
    """
    # No leading dashes in the pattern — pgrep would parse them as its own options.
    pids = set(_out(["pgrep", "-f", f"user-data-dir={profile_dir}"]).split())
    if not pids:
        return
    names = _out(["dbus-send", "--session", "--print-reply",
                  "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus",
                  "org.freedesktop.DBus.ListNames"])
    for name, pid in re.findall(r'"(org\.mpris\.MediaPlayer2\.\S+\.instance(\d+))"', names):
        if pid in pids:
            _do(["dbus-send", "--session", f"--dest={name}",
                 "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player.Pause"])
