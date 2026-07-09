#!/usr/bin/env bash
# chud installer. Installs the CLI, the OS window tools, and runs onboarding.
# All install paths converge here → `chud setup`.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf "\033[1;36m==>\033[0m %s\n" "$1"; }
warn() { printf "\033[1;33m!  \033[0m %s\n" "$1"; }

# 1. Python CLI --------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install it and re-run." >&2
  exit 1
fi

say "Installing the chud CLI"
if command -v pipx >/dev/null 2>&1; then
  pipx install --force "$REPO_DIR"
else
  python3 -m pip install --user "$REPO_DIR"
fi

# 2. OS window tools ---------------------------------------------------------
OS="$(uname -s)"
if [ "$OS" = "Linux" ]; then
  if [ "${XDG_SESSION_TYPE:-}" = "wayland" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    warn "Wayland session detected — chud needs X11. Log in with an 'Xorg' session."
  fi
  MISSING=()
  command -v wmctrl >/dev/null 2>&1 || MISSING+=(wmctrl)
  command -v xdotool >/dev/null 2>&1 || MISSING+=(xdotool)
  if [ "${#MISSING[@]}" -gt 0 ]; then
    say "Installing window tools: ${MISSING[*]}"
    if command -v apt-get >/dev/null 2>&1; then
      sudo apt-get update -qq && sudo apt-get install -y "${MISSING[@]}"
    elif command -v dnf >/dev/null 2>&1; then
      sudo dnf install -y "${MISSING[@]}"
    elif command -v pacman >/dev/null 2>&1; then
      sudo pacman -S --noconfirm "${MISSING[@]}"
    else
      warn "Install these manually: ${MISSING[*]}"
    fi
  fi
elif [ "$OS" = "Darwin" ]; then
  warn "macOS: grant Accessibility permission to your terminal/editor when first prompted."
fi

# 3. Onboarding --------------------------------------------------------------
say "Running setup"
chud setup

say "Done."
