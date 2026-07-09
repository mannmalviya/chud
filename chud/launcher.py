"""Launch the phone-sized Chrome window, and generate its home-screen launcher page.

We kill any previous phone for our dedicated profile before launching, so Chrome's
single-instance-per-profile behavior can't turn a new launch into "just a tab in the
old window" — each launch is a clean, independent app window.
"""
from __future__ import annotations

import html
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .backends import PHONE_MARKER
from .platform import chrome_binary, os_name


# The home-screen page ships as package data (chud/home.html) so it gets real
# HTML/CSS/JS editor tooling; home_url() fills in its {{...}} slots.
_HOME_TMPL = resources.files("chud").joinpath("home.html").read_text(encoding="utf-8")


def _tile(name: str, url: str) -> str:
    host = urlparse(url).netloc or url
    letter = html.escape((name or "?")[0].upper())
    return (
        f'<a href="{html.escape(url, quote=True)}"><div class="ico"><span>{letter}</span>'
        f'<img src="https://www.google.com/s2/favicons?domain={html.escape(host, quote=True)}&amp;sz=64"'
        # The letter is only a fallback — favicons are often transparent, so hide
        # it once the real icon arrives instead of layering them.
        f' onload="this.previousElementSibling.style.display=\'none\'" onerror="this.remove()" alt=""></div>'
        f'<div class="label">{html.escape(name)}</div></a>'
    )


def _history_urls(profile_dir: str, limit: int = 40) -> list[str]:
    """Most-recently-visited URLs from the phone's own Chrome history, so Recent
    reflects what's actually browsed in the phone — tile taps and in-app
    navigation never pass through the CLI, only `chud app` launches do.
    Chrome keeps the live DB locked, so query a throwaway copy; any failure
    just means history contributes nothing."""
    db = Path(profile_dir) / "Default" / "History"
    if not db.exists():
        return []
    fd, tmp = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    try:
        shutil.copyfile(db, tmp)
        con = sqlite3.connect(tmp)
        try:
            rows = con.execute(
                "SELECT url FROM urls WHERE url LIKE 'http%' "
                "ORDER BY last_visit_time DESC LIMIT ?", (limit,)).fetchall()
        finally:
            con.close()
        return [r[0] for r in rows]
    except (OSError, sqlite3.Error):
        return []
    finally:
        os.unlink(tmp)


def home_url() -> str:
    """(Re)generate the phone's home screen — a grid of favorites + recents the user
    can tap to switch apps inside the phone — and return its file:// URL."""
    cfg = config.load_config()
    st = config.load_state()
    favs = cfg.get("sites", [])
    fav_urls = {s["url"] for s in favs}

    def _host(u: str) -> str:
        return urlparse(u).netloc.removeprefix("www.")

    # One recent per site: candidates hold full URLs (e.g. two YouTube watch
    # links), so dedupe by host and skip hosts already shown as favorites.
    # Real browsing history first (freshest ordering), CLI launches as fallback.
    candidates = _history_urls(cfg["profile_dir"]) + st.get("recents", [])
    rec, seen = [], {_host(s["url"]) for s in favs}
    for u in candidates:
        h = _host(u)
        if u in fav_urls or not h or h in seen:
            continue
        seen.add(h)
        rec.append(u)
    rec = rec[:8]
    add_tile = ('<a href="#" id="add" title="Add an app"><div class="ico"><span>+</span></div>'
                '<div class="label">Add</div></a>')
    grids = ('<div class="grid" id="fav">'
             + "".join(_tile(s["name"], s["url"]) for s in favs) + add_tile + "</div>")
    if rec:
        grids += '<h2>Recent</h2><div class="grid">' + "".join(
            _tile(_host(u) or u, u) for u in rec) + "</div>"
    path = config.DIR / "home.html"
    config.DIR.mkdir(parents=True, exist_ok=True)
    shortcut_keys = [p.strip() for p in cfg["toggle_shortcut"].split("+") if p.strip()]
    page = (_HOME_TMPL.replace("{{grids}}", grids)
            .replace("{{catalog}}", json.dumps(config.KNOWN_SITES))
            .replace("{{present}}", json.dumps(sorted(fav_urls)))
            .replace("{{shortcut_kbds}}",
                     "+".join(f"<kbd>{html.escape(k)}</kbd>" for k in shortcut_keys))
            .replace("{{shortcut_json}}", json.dumps(shortcut_keys)))
    path.write_text(page)
    return path.as_uri()


def _kill_existing(profile_dir: str) -> None:
    name = os_name()
    if name in ("linux", "macos"):
        # No leading dashes in the pattern — pkill would parse them as its own options.
        subprocess.run(["pkill", "-f", f"user-data-dir={profile_dir}"],
                       capture_output=True, text=True)
    elif name == "windows":
        subprocess.run(["taskkill", "/F", "/FI", f"WINDOWTITLE eq *{PHONE_MARKER}*"],
                       capture_output=True, text=True)


def _strip_browser_frame(profile_dir: str) -> None:
    """Turn off Chrome's self-drawn title bar (the tab-like strip) for the phone
    profile, deferring decorations to the window manager — which the X11 backend
    then strips too, leaving a bare phone-shaped screen. Must run between kill
    and launch: Chrome rewrites Preferences on shutdown, so wait for the old
    phone to fully exit or our edit would be overwritten."""
    if os_name() != "linux":
        return
    for _ in range(20):
        r = subprocess.run(["pgrep", "-f", f"user-data-dir={profile_dir}"],
                           capture_output=True, text=True)
        if not r.stdout.strip():
            break
        time.sleep(0.1)
    prefs = Path(profile_dir) / "Default" / "Preferences"
    try:
        data = json.loads(prefs.read_text()) if prefs.exists() else {}
    except (OSError, ValueError):
        return
    if data.setdefault("browser", {}).get("custom_chrome_frame") is False:
        return
    data["browser"]["custom_chrome_frame"] = False
    try:
        prefs.parent.mkdir(parents=True, exist_ok=True)
        prefs.write_text(json.dumps(data))
    except OSError:
        pass


def launch(url: str) -> None:
    chrome = chrome_binary()
    if not chrome:
        raise RuntimeError("Chrome/Chromium not found on PATH. Install Google Chrome.")

    cfg = config.load_config()
    profile = cfg["profile_dir"]
    w, h = cfg["size"]
    x, y = cfg["position"]

    _kill_existing(profile)
    _strip_browser_frame(profile)

    args = [
        chrome,
        f"--app={url}",
        f"--user-data-dir={profile}",
        f"--window-size={w},{h}",
        f"--window-position={x},{y}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if os_name() == "linux":
        # Stable WM_CLASS so the backend can find this window by class, not title.
        args.append(f"--class={PHONE_MARKER}")

    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    if not url.startswith("file://"):  # the home screen itself isn't a "recent"
        config.push_recent(url)
