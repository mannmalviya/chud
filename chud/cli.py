"""chud command-line interface.

Every agent hook and the user drive the same commands here, so behavior lives in
exactly one place.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

from . import backends, config, hooks, launcher, onboarding
from .platform import (
    chrome_binary,
    is_wayland,
    os_name,
    supported,
    window_tool_status,
)


# User input within this window means they're actively working — a hook-driven
# phone raise would land on top of their typing.
ACTIVE_INPUT_MS = 10_000


# ---------------------------------------------------------------- helpers

def _guard_supported() -> bool:
    ok, detail = supported()
    if not ok:
        print(detail, file=sys.stderr)
    return ok


def _resolve(target: str) -> str:
    """A configured site name, or a raw URL."""
    cfg = config.load_config()
    for s in cfg.get("sites", []) + config.KNOWN_SITES:
        if s["name"].lower() == target.lower():
            return s["url"]
    if "://" in target:
        return target
    return "https://" + target


def _raise_phone_settle() -> None:
    """Raise the phone, retrying while the freshly-launched window maps."""
    for _ in range(20):
        if backends.phone_exists() is not False:  # True or None (unknown)
            backends.raise_phone()
            if backends.phone_exists():
                return
        time.sleep(0.2)
    backends.raise_phone()


def _watcher_pid() -> int | None:
    """The live focus-watcher's pid, or None. Verified against /proc cmdline so
    a recycled pid from an old session is never mistaken for ours."""
    pid = config.load_state().get("watcher_pid")
    if not pid:
        return None
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"watch-focus" in f.read():
                return pid
    except OSError:
        pass
    return None


def _spawn_focus_watcher() -> None:
    """Detached helper that minimizes the phone whenever the user focuses
    another window (see backends.watch_focus). It lives as long as the phone
    window does; supersede any earlier one so they don't accumulate."""
    if os_name() != "linux":
        return
    # Kill by remembered pid, not pkill -f — a pattern match can hit unrelated
    # processes whose command line merely mentions the watcher. Take the whole
    # process group so the xprop -spy child dies too.
    old = _watcher_pid()
    if old:
        try:
            os.killpg(old, signal.SIGTERM)
        except OSError:
            pass
    script = shutil.which("chud")
    argv = [script] if script else [sys.executable, "-m", "chud"]
    proc = subprocess.Popen(argv + ["watch-focus"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    config.update_state(watcher_pid=proc.pid)


def _ensure_phone(url: str) -> None:
    exists = backends.phone_exists()
    st = config.load_state()
    # A phone launched moments ago may not have mapped its X window yet, so
    # "doesn't exist" is stale — relaunching would kill the one still starting.
    if exists is False and time.time() - st.get("phone_launch_ts", 0) < 10:
        return
    if exists is False or (exists is None and not st.get("phone_launched")):
        launcher.launch(url)
        config.update_state(phone_launched=True, phone_launch_ts=time.time())


# ---------------------------------------------------------------- commands

def cmd_setup(a) -> None:
    onboarding.run(mode=a.mode, sites_csv=a.sites)


def cmd_doctor(_a) -> None:
    ok, detail = supported()
    tool_ok, tool_msg = window_tool_status()
    chrome = chrome_binary()
    print(f"OS:           {os_name()}")
    print(f"session:      {'wayland' if is_wayland() else 'x11/native'}")
    print(f"supported:    {'yes — ' + detail if ok else 'NO'}")
    if not ok:
        print("  " + detail.replace("\n", "\n  "))
    print(f"chrome:       {chrome or 'NOT FOUND (install Google Chrome)'}")
    print(f"window tool:  {tool_msg}")
    idle = backends.user_idle_ms()
    print(f"idle detect:  {f'ok ({idle} ms)' if idle is not None else 'unavailable — install xprintidle so the phone never pops over active typing'}")
    print(f"config:       {config.CONFIG_PATH} ({'exists' if config.config_exists() else 'not set up'})")


def cmd_session_init(_a) -> None:
    if not supported()[0]:
        return  # stay silent on unsupported machines
    cfg = config.load_config()
    mode = cfg.get("default_mode", "focus")
    handle = backends.capture_work()
    config.update_state(work_window=handle, armed=(mode == "always"),
                        phone_launched=False, snoozed=False)
    if mode == "focus":
        print("📵 chud: focus mode — phone off. Run `chud on` for a break.")
    elif mode == "ask":
        print("🧠 chud: enable the break phone this session? Run `chud on`.")


def cmd_on(_a) -> None:
    config.update_state(armed=True, snoozed=False)
    print("🧠 chud: armed — the phone will appear while the agent works.")


def cmd_off(_a) -> None:
    config.update_state(armed=False)
    print("📵 chud: focus mode.")


def cmd_phone(a) -> None:
    if not supported()[0]:
        return
    st = config.load_state()
    if a.if_armed and not st.get("armed"):
        return
    if a.if_armed and not a.if_hidden and st.get("snoozed"):
        # A new prompt always ends the snooze, even when the raise below is
        # suppressed because the user is still typing.
        st = config.update_state(snoozed=False)
    if a.if_armed and not backends.phone_focused():
        # Hook-driven raise. If the user is actively typing or mousing in
        # another window, popping the phone over them would interrupt — skip.
        # The every-tool hook retries, so the phone appears at the first hook
        # after their input has gone quiet for a beat.
        idle = backends.user_idle_ms()
        if idle is not None and idle < ACTIVE_INPUT_MS:
            return
    if a.if_hidden:
        # The every-tool hook. A snoozed phone means the user deliberately
        # clicked away mid-generation — stay hidden until the next prompt.
        if st.get("snoozed"):
            return
        if not backends.phone_hidden():
            # Already up — don't churn focus. But the phone being up means a
            # watcher should be alive; respawn if it died.
            if not _watcher_pid():
                _spawn_focus_watcher()
            return
        # "Hidden" because the window is gone entirely: the every-tool hook only
        # restores a minimized phone. Relaunching here would resurrect a phone
        # the user deliberately closed, on every subsequent tool call.
        if backends.phone_exists() is False:
            return
    # A deliberate raise (prompt hook or manual command) ends any snooze.
    config.update_state(snoozed=False)
    # Fresh launches open on the home screen — a tappable grid of the user's apps.
    _ensure_phone(launcher.home_url())
    _raise_phone_settle()
    _spawn_focus_watcher()


def cmd_work(_a) -> None:
    if not supported()[0]:
        return
    st = config.load_state()
    # The user is actively on the phone — don't yank it away mid-scroll just
    # because the agent finished or wants attention. The focus watcher swaps
    # back to work whenever they click away.
    if backends.phone_focused():
        return
    backends.pause_phone_media(config.load_config()["profile_dir"])
    backends.minimize_phone()
    backends.raise_work(st.get("work_window"))


def cmd_watch_focus(_a) -> None:
    backends.watch_focus(config.load_config()["profile_dir"],
                         on_user_hide=lambda: config.update_state(snoozed=True))


def cmd_app(a) -> None:
    if not _guard_supported():
        return
    url = _resolve(a.target)
    launcher.launch(url)
    config.update_state(phone_launched=True)
    _raise_phone_settle()
    _spawn_focus_watcher()


def cmd_info(_a) -> None:
    cfg = config.load_config()
    st = config.load_state()
    ok, _ = supported()
    print(json.dumps({
        "mode": cfg.get("default_mode"),
        "sites": cfg.get("sites", []),
        "recents": st.get("recents", []),
        "armed": st.get("armed", False),
        "supported": ok,
    }, indent=2))


def cmd_config(a) -> None:
    cfg = config.load_config()
    changed = False
    if a.set_mode:
        if a.set_mode not in ("focus", "always", "ask"):
            print("mode must be one of: focus, always, ask", file=sys.stderr)
            return
        cfg["default_mode"] = a.set_mode
        changed = True
    if a.sites is not None:
        cfg["sites"] = onboarding._sites_from_csv(a.sites)
        changed = True
    if changed:
        config.save_config(cfg)
        print("updated", config.CONFIG_PATH)
        return
    if a.edit:
        editor = os.environ.get("EDITOR", "nano")
        config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not config.CONFIG_PATH.exists():
            config.save_config(cfg)
        subprocess.call([editor, str(config.CONFIG_PATH)])
        return
    # default: show
    print(json.dumps(cfg, indent=2))


def cmd_uninstall(_a) -> None:
    hooks.remove_all()
    print("Removed chud hooks from Claude Code + Codex.")
    print(f"Config left at {config.DIR} (delete it manually to fully remove).")


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="chud", description="Floating phone browser that swaps with your work window while a coding agent generates.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("setup", help="onboarding: pick mode + sites, install hooks")
    s.add_argument("--mode", choices=["focus", "always", "ask"])
    s.add_argument("--sites", help="comma-separated site names or URLs")
    s.set_defaults(func=cmd_setup)

    sub.add_parser("doctor", help="check OS/session/chrome/tools").set_defaults(func=cmd_doctor)
    sub.add_parser("session-init", help="(hook) capture work window + set armed from mode").set_defaults(func=cmd_session_init)
    sub.add_parser("on", help="arm the phone for this session").set_defaults(func=cmd_on)
    sub.add_parser("off", help="focus mode for this session").set_defaults(func=cmd_off)

    ph = sub.add_parser("phone", help="bring the phone up (launch if needed)")
    ph.add_argument("--if-armed", action="store_true", dest="if_armed", help="no-op unless armed (used by the prompt hook)")
    ph.add_argument("--if-hidden", action="store_true", dest="if_hidden", help="no-op unless the phone is minimized/absent (used by the tool hook)")
    ph.set_defaults(func=cmd_phone)

    sub.add_parser("work", help="focus back to the work window").set_defaults(func=cmd_work)
    sub.add_parser("watch-focus", help="(internal) minimize the phone once focus moves to another window").set_defaults(func=cmd_watch_focus)

    for name in ("app", "launch"):
        ap = sub.add_parser(name, help="open a site in the phone (name or URL)")
        ap.add_argument("target")
        ap.set_defaults(func=cmd_app)

    sub.add_parser("info", help="print mode/sites/recents/armed as JSON").set_defaults(func=cmd_info)

    cf = sub.add_parser("config", help="show or edit config")
    cf.add_argument("--set-mode", dest="set_mode", choices=["focus", "always", "ask"])
    cf.add_argument("--sites", help="replace the site list (comma-separated)")
    cf.add_argument("--edit", action="store_true", help="open config in $EDITOR")
    cf.set_defaults(func=cmd_config)

    sub.add_parser("uninstall", help="remove the agent hooks").set_defaults(func=cmd_uninstall)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
