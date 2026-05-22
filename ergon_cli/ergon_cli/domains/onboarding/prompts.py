"""Lightweight interactive prompts using only the stdlib."""

import getpass
import os
import sys


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    isatty = getattr(sys.stdout, "isatty", None)  # slopcop: ignore[no-hasattr-getattr]
    return callable(isatty) and isatty()


_BOLD = "\033[1m" if _supports_color() else ""
_DIM = "\033[2m" if _supports_color() else ""
_RESET = "\033[0m" if _supports_color() else ""


def _parse_int_list(raw: str) -> list[int] | None:
    result: list[int] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped.isdigit():
            return None
        result.append(int(stripped))
    return result


def select_multiple(prompt: str, options: list[tuple[str, str]]) -> list[str]:
    print(f"\n{_BOLD}{prompt}{_RESET}")
    for index, (_id, label) in enumerate(options, 1):
        print(f"  {_BOLD}{index}{_RESET}) {label}")
    print(f"  {_DIM}Enter numbers separated by commas, or 'all'{_RESET}")

    while True:
        raw = input("> ").strip()
        if not raw:
            continue
        if raw.lower() == "all":
            return [_id for _id, _ in options]
        indices = _parse_int_list(raw)
        if indices and all(1 <= index <= len(options) for index in indices):
            return [options[index - 1][0] for index in indices]
        print(f"  {_DIM}Please enter valid numbers (1-{len(options)}) or 'all'{_RESET}")


def select_one(prompt: str, options: list[tuple[str, str]]) -> str:
    print(f"\n{_BOLD}{prompt}{_RESET}")
    for index, (_id, label) in enumerate(options, 1):
        print(f"  {_BOLD}{index}{_RESET}) {label}")

    while True:
        raw = input("> ").strip()
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(options):
                return options[index - 1][0]
        print(f"  {_DIM}Please enter a number (1-{len(options)}){_RESET}")


def confirm(prompt: str, default: bool = False) -> bool:
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
