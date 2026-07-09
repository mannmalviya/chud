"""Install/remove the agent triggers.

Claude Code: merge hook entries into ~/.claude/settings.json (JSON, structured merge).
Codex:       set the root `notify` key in ~/.codex/config.toml to a small dispatch
             script we generate. Both operations are idempotent and reversible.
Hotkey:      register the `chud toggle` global shortcut as a GNOME custom
             keybinding via gsettings (other desktops: bind it manually).

Every hook command routes through this same CLI, so all the behavior lives in one
place and re-running setup never duplicates entries.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

from . import config

HOME = Path.home()
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
CODEX_CONFIG = HOME / ".codex" / "config.toml"
CODEX_NOTIFY_SCRIPT = config.DIR / "codex-notify.sh"

# Marker embedded in every command we add, so uninstall can find & strip our entries.
MARK = "chud"

# (event, matcher, CLI subcommand); matcher None = all. An event may appear
# more than once with different matchers.
CLAUDE_EVENTS = [
    ("SessionStart", None, "session-init"),
    ("UserPromptSubmit", None, "phone --if-armed"),
    # NOTE: no PermissionRequest hook — it fires on every permission *evaluation*
    # (including silent auto-approvals before each tool), not just visible dialogs.
    # Visible approval dialogs arrive via Notification (type permission_prompt).
    ("Stop", None, "work"),
    ("Notification", None, "work"),
    ("PreToolUse", "AskUserQuestion", "work"),  # agent asks the user a question
    # The user answered the question — that Enter is a hand-off back to the
    # agent, so give them the phone immediately (same as a prompt submit).
    ("PostToolUse", "AskUserQuestion", "phone --if-armed"),
    # Any tool completing means the agent is working again (e.g. right after the
    # user approved a permission dialog) — re-raise the phone, but only if hidden.
    ("PostToolUse", None, "phone --if-armed --if-hidden"),
]


def cli_prefix() -> str:
    """Best way to invoke this CLI from a hook. Prefer the console script if it's on
    PATH; otherwise fall back to `python -m chud` with the current interpreter
    (works for editable/dev installs)."""
    found = shutil.which("chud")
    if found:
        return found
    return f'"{sys.executable}" -m chud'


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _is_ours(group: dict) -> bool:
    # Match both invocation forms: the console script ("chud") and the
    # module fallback ("python -m chud").
    for h in group.get("hooks", []):
        cmd = h.get("command", "")
        if "chud" in cmd or "chud" in cmd:
            return True
    return False


def install_claude_hooks() -> None:
    settings = _load_json(CLAUDE_SETTINGS)
    hooks = settings.setdefault("hooks", {})
    prefix = cli_prefix()
    # Drop every prior chud group first (across all events, so entries for
    # events we no longer use don't linger), then append the current set.
    for event in list(hooks):
        hooks[event] = [g for g in hooks[event] if not _is_ours(g)]
    for event, matcher, sub in CLAUDE_EVENTS:
        group = {"hooks": [{"type": "command", "command": f"{prefix} {sub}"}]}
        if matcher:
            group["matcher"] = matcher
        hooks.setdefault(event, []).append(group)
    _save_json(CLAUDE_SETTINGS, settings)


def remove_claude_hooks() -> None:
    if not CLAUDE_SETTINGS.exists():
        return
    settings = _load_json(CLAUDE_SETTINGS)
    hooks = settings.get("hooks", {})
    for event in list(hooks.keys()):
        hooks[event] = [g for g in hooks[event] if not _is_ours(g)]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    _save_json(CLAUDE_SETTINGS, settings)


def write_codex_notify_script() -> Path:
    config.DIR.mkdir(parents=True, exist_ok=True)
    prefix = cli_prefix()
    script = f"""#!/usr/bin/env bash
# chud: raise the work window when Codex finishes a turn or needs approval.
payload="$1"
type=$(printf '%s' "$payload" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("type",""))' 2>/dev/null)
case "$type" in
  agent-turn-complete|approval-requested) {prefix} work ;;
esac
"""
    CODEX_NOTIFY_SCRIPT.write_text(script)
    CODEX_NOTIFY_SCRIPT.chmod(CODEX_NOTIFY_SCRIPT.stat().st_mode | stat.S_IEXEC)
    return CODEX_NOTIFY_SCRIPT


def install_codex_notify() -> None:
    script = write_codex_notify_script()
    notify_line = f'notify = ["bash", "{script}"]'
    CODEX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    text = CODEX_CONFIG.read_text() if CODEX_CONFIG.exists() else ""
    if re.search(r"(?m)^\s*notify\s*=", text):
        # Replace an existing root-level notify line in place.
        text = re.sub(r"(?m)^\s*notify\s*=.*$", notify_line, text, count=1)
    else:
        # Root keys must precede any [table]; prepend.
        text = notify_line + "\n" + text
    CODEX_CONFIG.write_text(text)


def remove_codex_notify() -> None:
    if CODEX_CONFIG.exists():
        text = CODEX_CONFIG.read_text()
        if MARK in text or "codex-notify.sh" in text:
            text = re.sub(r"(?m)^\s*notify\s*=.*codex-notify\.sh.*$\n?", "", text)
            CODEX_CONFIG.write_text(text)
    CODEX_NOTIFY_SCRIPT.unlink(missing_ok=True)


# ------------------------------------------------------------- toggle hotkey

HOTKEY_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
HOTKEY_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/chud/"
HOTKEY_KB = f"{HOTKEY_SCHEMA}.custom-keybinding:{HOTKEY_PATH}"

_MODS = {"ctrl": "<Ctrl>", "control": "<Ctrl>", "alt": "<Alt>", "shift": "<Shift>",
         "super": "<Super>", "win": "<Super>", "meta": "<Super>", "cmd": "<Super>"}

MANUAL_HOTKEY_MSG = "bind `chud toggle` to a key in your desktop's keyboard settings"


def gnome_binding(shortcut: str) -> str | None:
    """'Ctrl+Alt+P' -> '<Ctrl><Alt>p'. None if it isn't modifiers+one key."""
    mods, key = "", None
    for part in (p.strip() for p in shortcut.split("+")):
        if not part:
            continue
        if part.lower() in _MODS:
            mods += _MODS[part.lower()]
        elif key is None:
            key = part
        else:
            return None  # two non-modifier keys
    if not key or not mods:  # a bare key would shadow normal typing
        return None
    return mods + (key.lower() if len(key) == 1 else key)


def _gsettings(*args: str) -> str | None:
    """Run gsettings, returning stdout — or None when it's absent/failing
    (non-GNOME desktop), so callers can fall back to manual instructions.

    Always prefer the system binary: a conda/venv gsettings earlier on PATH
    has no dconf backend, so it silently writes to a keyfile GNOME never
    reads and the hotkey never registers."""
    gsettings = "/usr/bin/gsettings" if Path("/usr/bin/gsettings").exists() else "gsettings"
    try:
        r = subprocess.run([gsettings, *args], capture_output=True, text=True,
                           timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def _hotkey_paths() -> list[str] | None:
    out = _gsettings("get", HOTKEY_SCHEMA, "custom-keybindings")
    if out is None:
        return None
    # GVariant prints an empty typed array as "@as []".
    text = out.strip().removeprefix("@as").strip()
    try:
        return list(ast.literal_eval(text))
    except (ValueError, SyntaxError):
        return []


def install_hotkey(shortcut: str) -> tuple[bool, str]:
    """Bind `chud toggle` to `shortcut` globally. Returns (ok, human message)."""
    binding = gnome_binding(shortcut)
    if not binding:
        return False, f"can't parse {shortcut!r} — use modifiers+key, e.g. Ctrl+Alt+P"
    paths = _hotkey_paths()
    if paths is None:
        return False, f"no gsettings (non-GNOME desktop) — {MANUAL_HOTKEY_MSG}"
    if HOTKEY_PATH not in paths:
        if _gsettings("set", HOTKEY_SCHEMA, "custom-keybindings",
                      str(paths + [HOTKEY_PATH])) is None:
            return False, f"gsettings rejected the keybinding — {MANUAL_HOTKEY_MSG}"
    _gsettings("set", HOTKEY_KB, "name", "chud toggle")
    _gsettings("set", HOTKEY_KB, "command", f"{cli_prefix()} toggle")
    _gsettings("set", HOTKEY_KB, "binding", binding)
    return True, f"{shortcut} flips phone ↔ work (GNOME keybinding)"


def remove_hotkey() -> None:
    paths = _hotkey_paths()
    if not paths or HOTKEY_PATH not in paths:
        return
    _gsettings("set", HOTKEY_SCHEMA, "custom-keybindings",
               str([p for p in paths if p != HOTKEY_PATH]))
    _gsettings("reset-recursively", HOTKEY_KB)


def install_all() -> tuple[bool, str]:
    """Install every trigger; returns the hotkey status for the caller to report
    (the hooks are silent-success, the hotkey can legitimately need manual setup)."""
    install_claude_hooks()
    install_codex_notify()
    return install_hotkey(config.load_config()["toggle_shortcut"])


def remove_all() -> None:
    remove_claude_hooks()
    remove_codex_notify()
    remove_hotkey()
