"""Install/remove the agent triggers.

Claude Code: merge hook entries into ~/.claude/settings.json (JSON, structured merge).
Codex:       set the root `notify` key in ~/.codex/config.toml to a small dispatch
             script we generate. Both operations are idempotent and reversible.

Every hook command routes through this same CLI, so all the behavior lives in one
place and re-running setup never duplicates entries.
"""
from __future__ import annotations

import json
import re
import shutil
import stat
import sys
from pathlib import Path

from . import config

HOME = Path.home()
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"
CODEX_CONFIG = HOME / ".codex" / "config.toml"
CODEX_NOTIFY_SCRIPT = config.DIR / "codex-notify.sh"

# Marker embedded in every command we add, so uninstall can find & strip our entries.
MARK = "chud"

# event -> (matcher, CLI subcommand); matcher None = all
CLAUDE_EVENTS = {
    "SessionStart": (None, "session-init"),
    "UserPromptSubmit": (None, "phone --if-armed"),
    # NOTE: no PermissionRequest hook — it fires on every permission *evaluation*
    # (including silent auto-approvals before each tool), not just visible dialogs.
    # Visible approval dialogs arrive via Notification (type permission_prompt).
    "Stop": (None, "work"),
    "Notification": (None, "work"),
    "PreToolUse": ("AskUserQuestion", "work"),  # agent asks the user a question
    # Any tool completing means the agent is working again (e.g. right after the
    # user approved a permission dialog) — re-raise the phone, but only if hidden.
    "PostToolUse": (None, "phone --if-armed --if-hidden"),
}


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
    for event, (matcher, sub) in CLAUDE_EVENTS.items():
        groups = hooks.setdefault(event, [])
        # Drop any prior chud group so re-install doesn't stack duplicates.
        groups[:] = [g for g in groups if not _is_ours(g)]
        group = {"hooks": [{"type": "command", "command": f"{prefix} {sub}"}]}
        if matcher:
            group["matcher"] = matcher
        groups.append(group)
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


def install_all() -> None:
    install_claude_hooks()
    install_codex_notify()


def remove_all() -> None:
    remove_claude_hooks()
    remove_codex_notify()
