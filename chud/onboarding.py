"""First-run onboarding: pick a default mode and the quick-toggle sites.

Interactive when run from a terminal; also callable non-interactively via
--mode/--sites so scripted installs share the same code path.
"""
from __future__ import annotations

import sys

from . import config, hooks, tui
from .platform import supported, window_tool_status

_BANNER = """
 ██████╗██╗  ██╗██╗   ██╗██████╗
██╔════╝██║  ██║██║   ██║██╔══██╗
██║     ███████║██║   ██║██║  ██║
██║     ██╔══██║██║   ██║██║  ██║
╚██████╗██║  ██║╚██████╔╝██████╔╝
 ╚═════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝
"""

MODES = {
    "1": ("focus", "Off by default each session — opt in with `chud on` (recommended)"),
    "2": ("always", "On automatically every session"),
    "3": ("ask", "Ask at the start of each session"),
}


def _prompt_mode() -> str:
    options = [(name, desc) for name, desc in MODES.values()]
    if tui.capable():
        return options[tui.select("How should each coding session start?", options)][0]
    # plain fallback (no raw-input terminal)
    print("\nHow should each coding session start?")
    for k, (name, desc) in MODES.items():
        print(f"  {k}) {name:7} — {desc}")
    choice = input("Choose [1]: ").strip() or "1"
    return MODES.get(choice, MODES["1"])[0]


def _prompt_custom_urls() -> list[dict]:
    raw = input("  Custom URL(s), comma-separated (https://…): ").strip()
    sites = []
    for url in (u.strip() for u in raw.split(",")):
        if url:
            if "://" not in url:
                url = "https://" + url
            sites.append({"name": url.split("//")[-1].split("/")[0], "url": url})
    return sites


def _prompt_sites() -> list[dict]:
    if tui.capable():
        options = [(s["name"], s["url"]) for s in config.KNOWN_SITES]
        options.append(("Other…", "add your own URL"))
        other = len(options) - 1
        picked = tui.multiselect(
            "Which sites do you want on quick-toggle?",
            options,
            preselected=set(range(len(config.KNOWN_SITES))),
        )
        sites = [config.KNOWN_SITES[i] for i in picked if i != other]
        if other in picked:
            sites += _prompt_custom_urls()
        return sites or list(config.KNOWN_SITES)

    # plain fallback (no raw-input terminal)
    print("\nWhich sites do you want on quick-toggle? (comma-separated numbers)")
    for i, s in enumerate(config.KNOWN_SITES, 1):
        print(f"  {i}) {s['name']}")
    print(f"  {len(config.KNOWN_SITES) + 1}) Other (add your own URL)")
    raw = input(f"Choose [1-{len(config.KNOWN_SITES)}, default all]: ").strip()

    sites: list[dict] = []
    if not raw:
        sites = list(config.KNOWN_SITES)
    else:
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok.isdigit():
                continue
            idx = int(tok)
            if 1 <= idx <= len(config.KNOWN_SITES):
                sites.append(config.KNOWN_SITES[idx - 1])
            elif idx == len(config.KNOWN_SITES) + 1:
                sites += _prompt_custom_urls()
    return sites or list(config.KNOWN_SITES)


def _prompt_shortcut(default: str) -> str:
    """Global hotkey for `chud toggle`. Enter keeps the default."""
    while True:
        raw = input(f"\nShortcut to switch between chud and your agent [{default}]: ").strip() or default
        if hooks.gnome_binding(raw):
            return raw
        print("  format: modifiers+key, e.g. Ctrl+Alt+P or Super+Space")


def _login_tour(sites: list[dict]) -> None:
    """Open each chosen site in the phone so the user can log in once now.

    The phone's Chrome profile is persistent, so logins done here stick for
    every future session.
    """
    from . import launcher

    if tui.capable():
        options = [
            ("log in now", "opens each site in the phone; log in, then press enter here for the next"),
            ("later", "log in whenever the phone first opens a site"),
        ]
        now = tui.select("Log in to your sites? (one-time — the phone stays logged in)", options) == 0
    else:
        now = (input("\nLog in to your sites now? [Y/n]: ").strip().lower() or "y").startswith("y")
    if not now:
        return

    for i, site in enumerate(sites, 1):
        print(f"  ({i}/{len(sites)}) opening {site['name']} — log in in the phone window")
        try:
            launcher.launch(site["url"])
        except RuntimeError as exc:
            print(f"  couldn't open the phone: {exc}")
            return
        if input("      Enter for the next site (q to stop): ").strip().lower() == "q":
            break
    print("  ✔ logins saved in the phone's profile.")


def run(mode: str | None = None, sites_csv: str | None = None,
        shortcut: str | None = None) -> None:
    interactive = (mode is None and sites_csv is None and shortcut is None
                   and sys.stdin.isatty())

    if interactive:
        print(_BANNER)
        print("── chud setup ──")

    cfg = config.load_config()

    try:
        if mode:
            cfg["default_mode"] = mode
        elif interactive:
            cfg["default_mode"] = _prompt_mode()

        if sites_csv is not None:
            cfg["sites"] = _sites_from_csv(sites_csv)
        elif interactive:
            cfg["sites"] = _prompt_sites()

        if shortcut is not None:
            if hooks.gnome_binding(shortcut) is None:
                print(f"invalid --shortcut {shortcut!r} — use modifiers+key, e.g. Ctrl+Alt+P",
                      file=sys.stderr)
                raise SystemExit(2)
            cfg["toggle_shortcut"] = shortcut
        elif interactive:
            cfg["toggle_shortcut"] = _prompt_shortcut(cfg["toggle_shortcut"])
    except (KeyboardInterrupt, EOFError):
        print("\ncancelled — nothing saved.")
        raise SystemExit(130)

    config.save_config(cfg)

    # Wire the agent triggers + the global toggle hotkey.
    hotkey_ok, hotkey_msg = hooks.install_all()

    # Report environment health.
    ok, detail = supported()
    tool_ok, tool_msg = window_tool_status()
    print("\nSaved to", config.CONFIG_PATH)
    print(f"  mode:  {cfg['default_mode']}")
    print(f"  sites: {', '.join(s['name'] for s in cfg['sites'])}")
    print(f"  hotkey: {hotkey_msg}" if hotkey_ok else f"  hotkey: NOT registered — {hotkey_msg}")
    print(f"  platform: {'OK — ' + detail if ok else 'UNSUPPORTED'}")
    if not ok:
        print("   ", detail.replace("\n", "\n    "))
    print(f"  window tool: {tool_msg}")

    if interactive and ok and cfg["sites"]:
        try:
            print()
            _login_tour(cfg["sites"])
        except (KeyboardInterrupt, EOFError):
            print("\n  skipped — log in whenever the phone opens.")

    print("\nHooks installed for Claude Code + Codex. You're set.")
    if cfg["default_mode"] == "focus":
        print("Tip: run `chud on` when you want a break this session.")


def _sites_from_csv(csv: str) -> list[dict]:
    """Map a comma list of known names (or raw URLs) to site dicts."""
    by_name = {s["name"].lower(): s for s in config.KNOWN_SITES}
    out: list[dict] = []
    for tok in csv.split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.lower() in by_name:
            out.append(by_name[tok.lower()])
        elif "://" in tok or "." in tok:
            url = tok if "://" in tok else "https://" + tok
            name = url.split("//")[-1].split("/")[0]
            out.append({"name": name, "url": url})
    return out or list(config.KNOWN_SITES)
