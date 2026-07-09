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
from pathlib import Path
from urllib.parse import urlparse

from . import config
from .backends import PHONE_MARKER
from .platform import chrome_binary, os_name


_HOME_TMPL = r"""<!doctype html><html><head><meta charset="utf-8"><title>chud</title>
<style>
  :root{--fg:#1c1c1e;--dim:#00000073;--tile:clamp(46px,12vw,60px)}
  body.dark{--fg:#f2f4f8;--dim:#ffffff8c}
  body{margin:0;padding-top:24px;background:#fff;color:var(--fg);
       font-family:system-ui,sans-serif;transition:background .25s}
  #sbar{position:fixed;top:0;left:0;right:0;height:24px;z-index:5;
        display:flex;align-items:center;justify-content:space-between;
        padding:2px 14px 0;box-sizing:border-box;font-size:12.5px;
        font-weight:700;color:var(--fg);user-select:none;-webkit-user-select:none}
  .sicons{display:flex;gap:6px;align-items:center}
  .sig{display:flex;gap:1.5px;align-items:flex-end;height:10px}
  .sig i{width:2.5px;background:var(--fg);border-radius:1px}
  #sbar svg{width:15px;height:13px;display:block}
  .bat{position:relative;width:21px;height:10.5px;border:1.5px solid var(--fg);
       border-radius:3.5px;opacity:.95}
  .bat::after{content:"";position:absolute;right:-4.5px;top:2px;width:2px;
              height:4.5px;background:var(--fg);border-radius:0 1.5px 1.5px 0}
  .bat i{position:absolute;top:1.5px;bottom:1.5px;left:1.5px;width:72%;
         background:var(--fg);border-radius:1.5px}
  h1{font-size:12px;letter-spacing:.3em;text-transform:uppercase;color:var(--dim);
     text-align:center;margin:26px 0 4px}
  h2{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--dim);
     max-width:820px;margin:14px auto 0;padding:0 18px;box-sizing:border-box}
  .grid{display:grid;gap:16px 6px;padding:14px;max-width:820px;margin:0 auto;
        grid-template-columns:repeat(auto-fill,minmax(calc(var(--tile) + 24px),1fr))}
  a{display:flex;flex-direction:column;align-items:center;gap:6px;
    text-decoration:none;color:var(--fg)}
  .ico{position:relative;width:var(--tile);height:var(--tile);
       border-radius:calc(var(--tile)*.26);
       background:rgba(255,255,255,.55);border:1px solid rgba(255,255,255,.65);
       backdrop-filter:blur(18px) saturate(1.6);
       -webkit-backdrop-filter:blur(18px) saturate(1.6);
       display:flex;align-items:center;justify-content:center;
       font-size:calc(var(--tile)*.42);font-weight:700;color:var(--dim);
       box-shadow:0 4px 14px rgba(0,0,0,.12)}
  body.dark .ico{background:rgba(255,255,255,.13);border-color:rgba(255,255,255,.18);
       box-shadow:0 4px 14px rgba(0,0,0,.35)}
  .ico img{position:absolute;width:calc(var(--tile)*.63);height:calc(var(--tile)*.63)}
  .label{font-size:clamp(12px,calc(var(--tile)*.24),14px);font-weight:600;
         letter-spacing:.01em;max-width:calc(var(--tile) + 22px);overflow:hidden;
         text-overflow:ellipsis;white-space:nowrap}
  p{font-size:10px;color:var(--dim);text-align:center;margin:18px 0}
  kbd{display:inline-block;padding:0 5px;border-radius:4px;font-family:inherit;
      font-size:.95em;font-weight:600;color:var(--fg);
      background:rgba(128,128,128,.14);border:1px solid rgba(128,128,128,.38);
      border-bottom-width:2px}
  .hint{font-size:11px;line-height:2.1;margin:22px 12px}
  #cfg{position:fixed;top:28px;right:10px;width:32px;height:32px;border-radius:50%;
       border:none;background:transparent;color:var(--dim);padding:0;cursor:pointer;
       display:flex;align-items:center;justify-content:center}
  #cfg:hover{background:rgba(128,128,128,.18)}
  #cfg svg{width:17px;height:17px}
  .swatches{display:grid;grid-template-columns:repeat(auto-fill,minmax(38px,1fr));
            gap:12px;padding:8px 6px;justify-items:center}
  .sw{width:38px;height:38px;border-radius:50%;border:1px solid #3a4356;
      cursor:pointer;padding:0}
  .sw.on{outline:2px solid #3b82f6;outline-offset:2px}
  .grid a:focus{outline:none}
  .grid a:focus .ico{outline:2px solid #3b82f6;outline-offset:3px}
  .rm{position:absolute;top:-6px;right:-6px;width:18px;height:18px;border-radius:50%;
      background:#2a3040;color:#8b93a7;border:none;font-size:11px;line-height:1;
      display:none;cursor:pointer;padding:0}
  a:hover .rm{display:block}
  #ov{position:fixed;inset:0;background:#000a;display:flex;align-items:center;
      justify-content:center;z-index:9}
  #ov[hidden]{display:none}  /* our display:flex would otherwise defeat [hidden] */
  #sheet{background:#151a25;border:1px solid #232a3a;border-radius:14px;padding:12px;
         width:min(290px,calc(100vw - 36px));max-height:74vh;overflow:auto;
         box-shadow:0 12px 40px #000b}
  #sheet h3{margin:2px 6px 10px;font-size:11px;letter-spacing:.15em;
            text-transform:uppercase;color:#5b6478}
  .row{display:flex;align-items:center;gap:11px;padding:9px 10px;border-radius:9px;
       cursor:pointer;font-size:13px}
  .row:hover{background:#1f2634}
  .row img,.row .dot{width:22px;height:22px;border-radius:6px}
  .row .dot{background:#1a1f2b;display:flex;align-items:center;justify-content:center;
            font-size:13px;font-weight:700;color:#8b93a7}
  #sheet input{width:100%;box-sizing:border-box;margin:6px 0;padding:9px 10px;
               border-radius:9px;border:1px solid #2a3345;background:#0b0d12;
               color:#cfd6e4;font-size:13px;outline:none}
  .btns{display:flex;gap:8px;justify-content:flex-end;margin-top:4px}
  .btns button{border:none;border-radius:8px;padding:7px 14px;font-size:12px;
               cursor:pointer;background:#232a3a;color:#cfd6e4}
  .btns .go{background:#3b82f6;color:#fff}
  .srow{display:flex;align-items:center;justify-content:space-between;gap:11px;
        padding:7px 10px;font-size:12px;color:#8b93a7}
  .srow .keys{white-space:nowrap;color:#cfd6e4}
  #sheet kbd{color:#cfd6e4;background:#232a3a;border-color:#2f3950}
  .snote{margin:6px 10px 2px;font-size:10px;color:#5b6478}
</style></head><body>
<div id="sbar"><span id="clock"></span><span class="sicons">
<span class="sig"><i style="height:4px"></i><i style="height:6px"></i><i style="height:8px"></i><i style="height:10px"></i></span>
<svg viewBox="0 0 24 20" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"><path d="M3 8a13 13 0 0 1 18 0"/><path d="M7 12.5a7.5 7.5 0 0 1 10 0"/><circle cx="12" cy="17" r="1.6" fill="currentColor" stroke="none"/></svg>
<span class="bat"><i id="batfill"></i></span></span></div>
<button id="cfg" title="Settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg></button>
<h1>chud</h1>
{{grids}}
<p class="hint"><kbd>Alt</kbd>+<kbd>&#8592;</kbd> returns here from any app &nbsp;&middot;&nbsp; <kbd>Alt</kbd>+<kbd>&#8594;</kbd> forward<br>{{shortcut_kbds}} flips to your work</p>
<div id="ov" hidden><div id="sheet"></div></div>
<script>
// User-added apps live in localStorage (the phone's own Chrome profile) so the
// static home page can grow without a server; regeneration never wipes them.
const KEY = "chudCustomSites";
const fav = document.getElementById("fav");
const addBtn = document.getElementById("add");
const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
const save = s => localStorage.setItem(KEY, JSON.stringify(s));
function render() {
  document.querySelectorAll(".custom").forEach(el => el.remove());
  load().forEach((s, i) => {
    const a = document.createElement("a"); a.href = s.url; a.className = "custom";
    const ico = document.createElement("div"); ico.className = "ico";
    const span = document.createElement("span"); span.textContent = (s.name || "?")[0].toUpperCase();
    const img = document.createElement("img");
    img.src = "https://www.google.com/s2/favicons?domain=" + new URL(s.url).hostname + "&sz=64";
    img.onload = () => span.style.display = "none";
    img.onerror = () => img.remove();
    const rm = document.createElement("button"); rm.className = "rm"; rm.textContent = "×";
    rm.title = "Remove";
    rm.onclick = ev => { ev.preventDefault(); ev.stopPropagation();
                         const c = load(); c.splice(i, 1); save(c); render(); };
    ico.append(span, img, rm);
    const label = document.createElement("div"); label.className = "label"; label.textContent = s.name;
    a.append(ico, label);
    fav.insertBefore(a, addBtn);
  });
}
// "+" opens a picker sheet: the catalog apps not yet on the grid, then "Other…".
const CATALOG = {{catalog}};
const FAVS = {{present}};
const ov = document.getElementById("ov");
const sheet = document.getElementById("sheet");
ov.addEventListener("click", e => { if (e.target === ov) ov.hidden = true; });

function addRow(parent, iconHost, text, onclick) {
  const r = document.createElement("div"); r.className = "row";
  if (iconHost) {
    const img = document.createElement("img");
    img.src = "https://www.google.com/s2/favicons?domain=" + iconHost + "&sz=64";
    img.onerror = () => img.remove();
    r.append(img);
  } else {
    const dot = document.createElement("div"); dot.className = "dot"; dot.textContent = "+";
    r.append(dot);
  }
  const t = document.createElement("span"); t.textContent = text;
  r.append(t); r.onclick = onclick; parent.append(r);
}

function openSheet() {
  const have = new Set(FAVS.concat(load().map(s => s.url)));
  sheet.textContent = "";
  const h = document.createElement("h3"); h.textContent = "Add an app"; sheet.append(h);
  for (const s of CATALOG) {
    if (have.has(s.url)) continue;
    addRow(sheet, new URL(s.url).hostname, s.name, () => {
      const c = load(); c.push(s); save(c); render(); ov.hidden = true;
    });
  }
  addRow(sheet, null, "Other…", otherForm);
  ov.hidden = false;
}

function otherForm() {
  sheet.textContent = "";
  const h = document.createElement("h3"); h.textContent = "Add by URL"; sheet.append(h);
  const inp = document.createElement("input");
  inp.placeholder = "reddit.com or https://…";
  const btns = document.createElement("div"); btns.className = "btns";
  const cancel = document.createElement("button"); cancel.textContent = "Cancel";
  cancel.onclick = () => ov.hidden = true;
  const go = document.createElement("button"); go.className = "go"; go.textContent = "Add";
  const submit = () => {
    let url = inp.value.trim(); if (!url) return;
    if (!url.includes("://")) url = "https://" + url;
    let name;
    try { name = new URL(url).hostname.replace(/^www\./, ""); }
    catch { inp.value = ""; inp.placeholder = "invalid URL — try again"; return; }
    const c = load(); c.push({ name, url }); save(c); render(); ov.hidden = true;
  };
  go.onclick = submit;
  inp.addEventListener("keydown", e => { if (e.key === "Enter") submit(); });
  btns.append(cancel, go);
  sheet.append(inp, btns);
  inp.focus();
}

// Wallpaper: a flat color in localStorage; text + icon glass adapt to its brightness.
const WKEY = "chudWallpaper";
const WALLS = ["#ffffff","#e9e9ef","#cfe3f5","#dcead9","#f5dee4",
               "#000000","#0b0d12","#182338","#2a1e3f","#123326"];
function applyWall(c) {
  document.body.style.background = c;
  const n = parseInt(c.slice(1), 16);
  const lum = (0.299*(n>>16&255) + 0.587*(n>>8&255) + 0.114*(n&255)) / 255;
  document.body.classList.toggle("dark", lum < 0.55);
}
applyWall(localStorage.getItem(WKEY) || "#ffffff");

// Status bar: live clock + real battery level (the window has no OS frame,
// so this bar is the phone's only "chrome").
const clockEl = document.getElementById("clock");
const tick = () => clockEl.textContent = new Date()
  .toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  .replace(/\s?[AP]M/i, "");
tick(); setInterval(tick, 10000);
navigator.getBattery?.().then(b => {
  const fill = document.getElementById("batfill");
  const upd = () => fill.style.width = Math.round(b.level * 100) + "%";
  upd(); b.addEventListener("levelchange", upd);
});

// The phone ↔ work hotkey, injected from ~/.chud/config.json at generation time.
const SHORTCUT = {{shortcut_json}};
document.getElementById("cfg").addEventListener("click", () => {
  sheet.textContent = "";
  const h = document.createElement("h3"); h.textContent = "Wallpaper"; sheet.append(h);
  const wrap = document.createElement("div"); wrap.className = "swatches";
  const cur = localStorage.getItem(WKEY) || "#ffffff";
  for (const c of WALLS) {
    const b = document.createElement("button");
    b.className = "sw" + (c === cur ? " on" : "");
    b.style.background = c;
    b.onclick = () => { localStorage.setItem(WKEY, c); applyWall(c);
                        wrap.querySelector(".on")?.classList.remove("on");
                        b.classList.add("on"); };
    wrap.append(b);
  }
  sheet.append(wrap);
  const sh = document.createElement("h3"); sh.textContent = "Shortcuts";
  sh.style.marginTop = "14px"; sheet.append(sh);
  for (const [keys, what] of [[["Alt", "←"], "back to this home screen"],
                              [["Alt", "→"], "forward into the app"],
                              [SHORTCUT, "flip phone ↔ work"],
                              [["Super", "drag"], "move the phone"]]) {
    const r = document.createElement("div"); r.className = "srow";
    const t = document.createElement("span"); t.textContent = what;
    const k = document.createElement("span"); k.className = "keys";
    keys.forEach((key, i) => {
      if (i) k.append("+");
      const el = document.createElement("kbd"); el.textContent = key; k.append(el);
    });
    r.append(t, k); sheet.append(r);
  }
  const note = document.createElement("div"); note.className = "snote";
  note.textContent = "rebind the flip key: chud config --set-shortcut";
  sheet.append(note);
  ov.hidden = false;
});

addBtn.addEventListener("click", e => { e.preventDefault(); openSheet(); });
render();

// Arrow keys walk the app tiles by moving native focus, so Enter opens the
// focused tile with the browser's own link handling. Left/Right follow
// reading order; Up/Down jump to the horizontally nearest tile in the
// adjacent row, which also carries focus across the Favorites/Recent grids.
const tiles = () => [...document.querySelectorAll(".grid a")];
function verticalMove(ts, cur, dir) {
  const c = ts[cur].getBoundingClientRect();
  const cands = ts.map((t, i) => ({ i, r: t.getBoundingClientRect() }))
    .filter(o => dir > 0 ? o.r.top > c.top + 1 : o.r.top < c.top - 1);
  if (!cands.length) return cur;
  const edge = dir > 0 ? Math.min(...cands.map(o => o.r.top))
                       : Math.max(...cands.map(o => o.r.top));
  return cands.filter(o => Math.abs(o.r.top - edge) < 1)
    .reduce((a, b) => Math.abs(b.r.left - c.left) < Math.abs(a.r.left - c.left) ? b : a).i;
}
document.addEventListener("keydown", e => {
  if (!ov.hidden) {           // a sheet is open — don't steal its keys,
    if (e.key === "Escape") ov.hidden = true;   // but let Esc close it
    return;
  }
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
  e.preventDefault();         // the page must never scroll instead
  const ts = tiles();
  if (!ts.length) return;
  let cur = ts.indexOf(document.activeElement);
  if (cur === -1) { ts[0].focus(); return; }
  if (e.key === "ArrowLeft") cur = Math.max(0, cur - 1);
  else if (e.key === "ArrowRight") cur = Math.min(ts.length - 1, cur + 1);
  else cur = verticalMove(ts, cur, e.key === "ArrowDown" ? 1 : -1);
  ts[cur].focus();
});
// Focus the first tile on every show (fresh load and Alt+← back-navigation
// alike) so arrows + Enter work without a click.
addEventListener("pageshow", () => tiles()[0]?.focus());
</script></body></html>
"""


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
