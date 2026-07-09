"""Minimal dependency-free terminal widgets: arrow-key select and multi-select.

Used by onboarding. Callers should check `capable()` and fall back to plain
numbered prompts when raw key input isn't available (pipes, dumb terminals).
"""
from __future__ import annotations

import os
import sys

HIDE = "\x1b[?25l"
SHOW = "\x1b[?25h"
RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
CYAN = "\x1b[36m"
GREEN = "\x1b[32m"


def capable() -> bool:
    """True if we can run the interactive widgets on this terminal."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if os.name == "nt":
        try:
            import msvcrt  # noqa: F401
        except ImportError:
            return False
        return True
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except ImportError:
        return False
    return True


_buf = bytearray()  # type-ahead not yet consumed (keys can arrive coalesced)


def _read_chunk() -> bytes:
    """Block until ≥1 byte of input; an arrow key arrives as one 3-byte chunk."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd, termios.TCSADRAIN)  # DRAIN keeps type-ahead (FLUSH drops it)
        return os.read(fd, 32)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key() -> str:
    """Block for one keypress → 'up'/'down'/'enter'/'space'/'esc' or the char."""
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):  # arrow keys arrive as a two-char sequence
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
        if ch == "\x03":
            raise KeyboardInterrupt
        if ch == "\r":
            return "enter"
        if ch == " ":
            return "space"
        if ch == "\x1b":
            return "esc"
        return ch

    if not _buf:
        _buf.extend(_read_chunk())
    b = _buf[0]
    if b == 0x1B:
        if len(_buf) >= 3 and _buf[1:2] == b"[":
            final = chr(_buf[2])
            del _buf[:3]
            return {"A": "up", "B": "down"}.get(final, "")
        if len(_buf) == 1:  # bare ESC
            del _buf[:1]
            return "esc"
        _buf.clear()  # some other escape sequence — ignore it whole
        return ""
    del _buf[:1]
    ch = chr(b) if b < 0x80 else ""
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    return ch


class _Screen:
    """Repaints a block of lines in place between keypresses."""

    def __init__(self) -> None:
        self.lines = 0

    def draw(self, lines: list[str]) -> None:
        out = sys.stdout
        if self.lines:
            out.write(f"\x1b[{self.lines}A")
        out.write("\r\x1b[J")  # clear from here down, then repaint
        out.write("\n".join(lines) + "\n")
        out.flush()
        self.lines = len(lines)


def select(title: str, options: list[tuple[str, str]], default: int = 0) -> int:
    """Single choice. `options` is [(label, description)]. Returns the index."""
    idx = default
    width = max(len(label) for label, _ in options)
    scr = _Screen()
    sys.stdout.write(HIDE)
    try:
        while True:
            lines = [f"{BOLD}{title}{RESET}"]
            for i, (label, desc) in enumerate(options):
                if i == idx:
                    lines.append(f"  {CYAN}❯ ● {label:<{width}}{RESET}  {DIM}{desc}{RESET}")
                else:
                    lines.append(f"    ○ {label:<{width}}  {DIM}{desc}{RESET}")
            lines.append(f"  {DIM}↑/↓ move · enter confirm{RESET}")
            scr.draw(lines)

            key = _read_key()
            if key in ("up", "k"):
                idx = (idx - 1) % len(options)
            elif key in ("down", "j"):
                idx = (idx + 1) % len(options)
            elif key.isdigit() and 1 <= int(key) <= len(options):
                idx = int(key) - 1
            elif key == "enter":
                scr.draw([f"{GREEN}✔{RESET} {title} {DIM}·{RESET} {CYAN}{options[idx][0]}{RESET}"])
                return idx
    finally:
        sys.stdout.write(SHOW)
        sys.stdout.flush()


def multiselect(title: str, options: list[tuple[str, str]], preselected: set[int] | None = None) -> list[int]:
    """Multiple choice with space-to-toggle. Returns the checked indices in order."""
    idx = 0
    checked = set(preselected or ())
    width = max(len(label) for label, _ in options)
    scr = _Screen()
    sys.stdout.write(HIDE)
    try:
        while True:
            lines = [f"{BOLD}{title}{RESET}"]
            for i, (label, desc) in enumerate(options):
                box = f"{GREEN}◼{RESET}" if i in checked else "◻"
                pointer = f"{CYAN}❯{RESET}" if i == idx else " "
                label_txt = f"{CYAN}{label:<{width}}{RESET}" if i == idx else f"{label:<{width}}"
                lines.append(f"  {pointer} {box} {label_txt}  {DIM}{desc}{RESET}")
            lines.append(f"  {DIM}↑/↓ move · space toggle · a all · enter confirm{RESET}")
            scr.draw(lines)

            key = _read_key()
            if key in ("up", "k"):
                idx = (idx - 1) % len(options)
            elif key in ("down", "j"):
                idx = (idx + 1) % len(options)
            elif key == "space":
                checked.symmetric_difference_update({idx})
            elif key == "a":
                checked = set() if len(checked) == len(options) else set(range(len(options)))
            elif key.isdigit() and 1 <= int(key) <= len(options):
                checked.symmetric_difference_update({int(key) - 1})
            elif key == "enter":
                picked = sorted(checked)
                summary = ", ".join(options[i][0] for i in picked) or "none"
                scr.draw([f"{GREEN}✔{RESET} {title} {DIM}·{RESET} {CYAN}{summary}{RESET}"])
                return picked
    finally:
        sys.stdout.write(SHOW)
        sys.stdout.flush()
