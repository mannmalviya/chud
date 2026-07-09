# chud

A phone-sized **real Chrome window** that hovers over your work while a coding agent
(Claude Code / Codex) is generating — so you can scroll TikTok, Instagram, Chess.com,
Lichess, or Tinder during the wait — and **snaps focus back to your editor the moment
the agent finishes or needs you.**

It's a real browser window, not an embed, so you get real login, real video, **real
audio**, and native performance. Off by default (focus mode); you opt in per session.

```
you submit a prompt ──▶ phone rises over your work ──▶ you scroll while the agent thinks
agent finishes / asks ──▶ focus snaps back to your editor
```

## How it works

- The phone is a normal OS window (`chrome --app`, phone-sized, its own persistent
  profile). Embedding real sites *inside* an editor is blocked by `X-Frame-Options`;
  a separate window sidesteps that entirely.
- A tiny CLI (`chud`) pins/raises windows via the OS: **Win32 / macOS
  Accessibility / X11 (`wmctrl`+`xdotool`)**.
- On Linux the phone is **frameless** — no title bar or browser chrome, just a
  bare phone-shaped screen with its own status bar (clock + battery) on the
  home screen. Move it with `Super`+drag.
- Agent **hooks** flip between the phone and your "work window" (the terminal or
  editor you launched the agent in, captured at session start):
  - **Claude Code** — `UserPromptSubmit` (and answering an agent question) raises
    the phone; finishing a turn, needing approval, or asking a question pauses the
    phone's media, minimizes it, and raises your work window.
  - **Codex** — its `notify` hook raises your work window on turn-complete / approval.
- The phone opens on a **home screen** — a tappable grid of your favorite +
  recent sites — so you can switch apps inside the phone. `Alt+←` returns to it,
  `Alt+→` goes back into the app (the home screen and its ⚙ settings show these).
- A **global hotkey** (`Ctrl+Alt+P` by default, customizable in setup or via
  `chud config --set-shortcut`) flips between the phone and your work window
  anytime, without waiting for a hook.

## Platform support

| | Windows | macOS | Linux (X11) | Linux (Wayland) |
|---|---|---|---|---|
| Supported | ✅ | ✅¹ | ✅ | ❌² |

¹ Needs a one-time Accessibility permission; always-on-top is approximate.
² Wayland forbids foreign-window control — log in with an **Xorg / X11** session.

## Install

Any of these — they all end at `chud setup`:

```bash
# 1) one-liner
curl -fsSL https://raw.githubusercontent.com/mannmalviya/chud/main/install.sh | bash

# 2) package manager
pipx install chud && chud setup

# 3) from a clone
git clone https://github.com/mannmalviya/chud && cd chud && ./install.sh
```

**Linux** also needs `wmctrl` + `xdotool` (the installer adds them):
`sudo apt install wmctrl xdotool`.

## Usage

```bash
chud setup        # onboarding: pick default mode + quick-toggle sites + hotkey
chud on           # arm the break-phone for this session
chud off          # focus mode
chud toggle       # flip phone ↔ work (bound globally, Ctrl+Alt+P by default)
chud app tiktok   # open a site in the phone (name or URL)
chud doctor       # check OS / session / chrome / tools
chud config       # show config;  --set-mode / --sites / --set-shortcut / --edit
chud uninstall    # remove the agent hooks + hotkey
```

**Default modes** (chosen in setup, editable anytime):
- `focus` — off each session; opt in with `chud on`. *(default)*
- `always` — armed automatically every session.
- `ask` — prompts each session.

Everything lives in `~/.chud/config.json` and is editable via
`chud config --edit`.

## For AI agents / Claude Code

If you're an AI coding agent asked to install this, do exactly:

1. Ensure `python3` and Google Chrome are present (`chud`'s `doctor` reports both).
2. Install the CLI: `pipx install "<repo>"` (or `python3 -m pip install --user "<repo>"`).
3. On Linux, ensure `wmctrl` and `xdotool` are installed (`apt`/`dnf`/`pacman`).
   If the session is Wayland (`echo $XDG_SESSION_TYPE`), tell the user to switch to X11 — it won't work otherwise.
4. Run `chud setup` (interactive) — or non-interactively:
   `chud setup --mode focus --sites "Instagram,TikTok,Chess.com"`.
5. Verify with `chud doctor`. Everything routes through the idempotent
   `chud setup`, so re-running is safe.

Do **not** hand-edit `~/.claude/settings.json` or `~/.codex/config.toml` — `setup`
merges the hooks for you and `uninstall` removes them cleanly.

## Uninstall

```bash
chud uninstall      # removes hooks from Claude Code + Codex
rm -rf ~/.chud       # removes config, state, and the phone's Chrome profile
```

## Caveats

- **Wayland** is unsupported (see above).
- **macOS** always-on-top is approximate and needs an Accessibility grant.
- **Codex** has no "turn started" event, so the phone auto-*hides* on turn-complete;
  raise it with the toggle hotkey (or `chud phone`) when you kick off a Codex turn.
- You're using the real sites in a real browser with your own login — no scraping.
  Personal use.

## License

MIT — see [LICENSE](LICENSE).
