"""Read, merge, and write ``.env`` files with section comments."""

from pathlib import Path

from ergon_cli.onboarding.profile import OnboardProfile


# Infra defaults that every .env should have — safe to set if missing.
_INFRA_DEFAULTS: dict[str, str] = {
    "INNGEST_EVENT_KEY": "dev",
    "INNGEST_DEV": "1",
    "INNGEST_API_BASE_URL": "http://localhost:8289",
}

# Ordered sections and the keys that belong to each.
_SECTIONS: list[tuple[str, list[str]]] = [
    ("Database", ["DATABASE_URL", "ERGON_DATABASE_URL"]),
    (
        "LLM Provider Keys",
        ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"],
    ),
    ("Sandbox", ["E2B_API_KEY"]),
    ("Search", ["EXA_API_KEY"]),
    ("GPU / Training", ["SHADEFORM_API_KEY", "LAMBDA_API_KEY", "RUNPOD_API_KEY"]),
    ("Inngest", ["INNGEST_EVENT_KEY", "INNGEST_DEV", "INNGEST_API_BASE_URL"]),
    (
        "Tailscale",
        ["TAILSCALE_AUTH_KEY", "TAILSCALE_MACBOOK_IP"],
    ),
]


def _read_existing(path: Path) -> dict[str, str]:
    """Parse an existing ``.env`` into a plain dict, ignoring comments."""
    pairs: dict[str, str] = {}
    if not path.exists():
        return pairs
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def _write_sectioned(path: Path, merged: dict[str, str]) -> None:
    """Write a ``.env`` grouped by section, only including keys that have values."""
    lines: list[str] = []
    written_keys: set[str] = set()

    for section_name, section_keys in _SECTIONS:
        section_lines: list[str] = []
        for key in section_keys:
            if key in merged and merged[key]:
                section_lines.append(f"{key}={merged[key]}")
                written_keys.add(key)
        if section_lines:
            if lines:
                lines.append("")
            lines.append(f"# === {section_name} ===")
            lines.extend(section_lines)

    # Preserve any unknown keys from the original file.
    leftover = {k: v for k, v in merged.items() if k not in written_keys and v}
    if leftover:
        if lines:
            lines.append("")
        lines.append("# === Other ===")
        for key, value in sorted(leftover.items()):
            lines.append(f"{key}={value}")

    lines.append("")  # trailing newline
    path.write_text("\n".join(lines))


def write_env(profile: OnboardProfile, path: Path) -> None:
    """Write ``.env`` from *profile*, merging with any existing file."""
    existing = _read_existing(path)

    merged = {**existing, **profile.keys}

    for key, default in _INFRA_DEFAULTS.items():
        merged.setdefault(key, default)

    _write_sectioned(path, merged)
