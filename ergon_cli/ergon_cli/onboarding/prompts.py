"""Lightweight interactive prompts using only the stdlib.

No third-party dependencies — just ``input()`` and ``getpass``.
ANSI bold/dim are used for readability but degrade gracefully.
"""

import getpass
import os
import sys


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    # sys.stdout always has isatty on CPython; guard for edge-case runtimes.
    isatty = getattr(sys.stdout, "isatty", None)  # slopcop: ignore[no-hasattr-getattr]
    return callable(isatty) and isatty()


_BOLD = "\033[1m" if _supports_color() else ""
_DIM = "\033[2m" if _supports_color() else ""
_RESET = "\033[0m" if _supports_color() else ""


def _parse_int_list(raw: str) -> list[int] | None:
    """Parse comma-separated integers.  Returns None on any parse failure."""
    parts = raw.split(",")
    result: list[int] = []
    for part in parts:
        stripped = part.strip()
        if not stripped.isdigit():
            return None
        result.append(int(stripped))
    return result


def select_multiple(prompt: str, options: list[tuple[str, str]]) -> list[str]:
    """Multi-select prompt.  Returns list of selected option IDs.

    ``options`` is a list of ``(id, label)`` tuples.  The user types
    comma-separated numbers (e.g. ``1,3``) or ``all``.
    """
    print(f"\n{_BOLD}{prompt}{_RESET}")
    for i, (_id, label) in enumerate(options, 1):
        print(f"  {_BOLD}{i}{_RESET}) {label}")
    print(f"  {_DIM}Enter numbers separated by commas, or 'all'{_RESET}")

    while True:
        raw = input("> ").strip()
        if not raw:
            continue
        if raw.lower() == "all":
            return [_id for _id, _ in options]
        indices = _parse_int_list(raw)
        if indices and all(1 <= idx <= len(options) for idx in indices):
            return [options[idx - 1][0] for idx in indices]
        print(f"  {_DIM}Please enter valid numbers (1-{len(options)}) or 'all'{_RESET}")


def select_one(prompt: str, options: list[tuple[str, str]]) -> str:
    """Single-select prompt.  Returns the chosen option ID."""
    print(f"\n{_BOLD}{prompt}{_RESET}")
    for i, (_id, label) in enumerate(options, 1):
        print(f"  {_BOLD}{i}{_RESET}) {label}")

    while True:
        raw = input("> ").strip()
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
        print(f"  {_DIM}Please enter a number (1-{len(options)}){_RESET}")


def confirm(prompt: str, default: bool = False) -> bool:
    """Yes/no prompt.  Returns True for yes."""
    suffix = "[Y/n]" if default else "[y/N]"
    print(f"\n{_BOLD}{prompt}{_RESET} {suffix}")

    while True:
        raw = input("> ").strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print(f"  {_DIM}Please enter y or n{_RESET}")


def ask_secret(env_var: str) -> str:
    """Prompt for an API key with masked input.

    Checks ``os.environ`` and existing ``.env`` first; if a value is already
    present, offers to keep it.
    """
    existing = os.environ.get(env_var, "")
    if existing:
        masked = existing[:4] + "..." + existing[-4:] if len(existing) > 12 else "***"
        keep = confirm(f"Found existing {env_var} ({masked}). Keep it?", default=True)
        if keep:
            return existing

    print(f"\n{_BOLD}{env_var}{_RESET}")
    while True:
        value = getpass.getpass("  Paste key (hidden): ").strip()
        if value:
            return value
        print(f"  {_DIM}Key cannot be empty{_RESET}")
