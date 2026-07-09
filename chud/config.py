"""Config + state store, both plain JSON under ~/.chud/.

config.json  — user preferences (edited via onboarding / `chud config`).
state.json   — runtime state (armed flag, captured work window, recents).

Kept separate so that editing preferences never races with per-session runtime writes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

HOME = Path.home()
DIR = HOME / ".chud"
CONFIG_PATH = DIR / "config.json"
STATE_PATH = DIR / "state.json"
PROFILE_DIR = DIR / "chrome-profile"
ICON_CACHE = DIR / "icons"

# The app catalog: shown in onboarding and in the home screen's "+" picker.
KNOWN_SITES = [
    {"name": "Instagram", "url": "https://www.instagram.com"},
    {"name": "TikTok", "url": "https://www.tiktok.com"},
    {"name": "Chess.com", "url": "https://www.chess.com"},
    {"name": "Lichess", "url": "https://lichess.org"},
    {"name": "Tinder", "url": "https://tinder.com"},
    {"name": "YouTube", "url": "https://www.youtube.com"},
    {"name": "Reddit", "url": "https://www.reddit.com"},
    {"name": "X", "url": "https://x.com"},
    {"name": "Twitch", "url": "https://www.twitch.tv"},
    {"name": "Netflix", "url": "https://www.netflix.com"},
]

DEFAULT_CONFIG = {
    "default_mode": "focus",  # focus | always | ask
    "sites": KNOWN_SITES[:5],  # Favorites shown in the launcher
    "position": [1500, 90],  # top-right-ish; overridden per screen at launch if absent
    "size": [412, 732],  # 9:16 — one reel/short fills the frame, no next-reel peek
    "profile_dir": str(PROFILE_DIR),
    "toggle_shortcut": "Ctrl+Alt+P",  # global hotkey for `chud toggle` (phone ↔ work)
}

DEFAULT_STATE = {
    "armed": False,
    "work_window": None,  # opaque platform handle captured at SessionStart
    "recents": [],  # list of urls, most-recent first
    "current_url": None,
    "snoozed": False,  # user clicked away mid-generation; don't re-raise until next prompt
}


def _read(path: Path, default: dict) -> dict:
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(default)
    # Fill in any keys added in newer versions.
    merged = dict(default)
    merged.update(data)
    return merged


def _write(path: Path, data: dict) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)  # atomic


def load_config() -> dict:
    return _read(CONFIG_PATH, DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    _write(CONFIG_PATH, cfg)


def config_exists() -> bool:
    return CONFIG_PATH.exists()


def load_state() -> dict:
    return _read(STATE_PATH, DEFAULT_STATE)


def save_state(state: dict) -> None:
    _write(STATE_PATH, state)


def update_state(**kwargs) -> dict:
    state = load_state()
    state.update(kwargs)
    save_state(state)
    return state


def push_recent(url: str, limit: int = 12) -> None:
    state = load_state()
    recents = [u for u in state.get("recents", []) if u != url]
    recents.insert(0, url)
    state["recents"] = recents[:limit]
    state["current_url"] = url
    save_state(state)
