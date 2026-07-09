<p align="center">
  <img src="assets/chud.png" alt="chud" width="420">
</p>

<h1 align="center">chud</h1>

<p align="center"><b>chud hovers over your editor while your coding agent thinks — and yanks you back the second it's done.</b></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/python-3.9+-3776AB.svg?logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux%20(X11)-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/works%20with-Claude%20Code%20%7C%20Codex-d97757.svg" alt="Works with Claude Code and Codex">
  <img src="https://img.shields.io/badge/browser-real%20Chrome%2C%20real%20audio-4285F4.svg?logo=googlechrome&logoColor=white" alt="Real Chrome">
  <a href="https://github.com/mannmalviya/chud/pulls"><img src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg" alt="PRs Welcome"></a>
</p>

---

```text
you submit a prompt ──▶ chud rises over your work ──▶ you scroll while the agent thinks
agent finishes / asks ──▶ focus snaps back to your editor
```

It's a **real Chrome window** — real logins, real video, real audio.
Scroll TikTok, Instagram, or play chess during the wait. When the agent finishes or
needs you, chud pauses its media, gets out of the way, and your editor takes focus.
Off by default; you opt in per session.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/mannmalviya/chud/main/install.sh | bash
```

or:

```bash
pipx install chud && chud setup
```

Linux needs `wmctrl` + `xdotool` (the installer adds them). Wayland is unsupported — use an X11 session.

### Install with Claude Code

Paste this into Claude Code:

```text
Install chud (https://github.com/mannmalviya/chud): pipx install chud
(or python3 -m pip install --user chud). On Linux, install wmctrl and
xdotool, and warn me if $XDG_SESSION_TYPE is wayland. Then run
`chud setup --mode focus --sites "Instagram,TikTok,Chess.com"` and
verify with `chud doctor`. Don't hand-edit ~/.claude/settings.json —
chud setup merges the hooks itself.
```

## Usage

```bash
chud on           # arm chud for this session
chud off          # focus mode
chud toggle       # flip chud ↔ work (global hotkey: Ctrl+Alt+P)
chud app tiktok   # open a site in chud
chud doctor       # check your setup
chud uninstall    # remove hooks + hotkey
```

Config lives in `~/.chud/config.json` (`chud config --edit`).

## License

MIT — see [LICENSE](LICENSE).
