"""Read, merge, and write ``.env`` files with section comments."""

from pathlib import Path

from ergon_cli.domains.onboarding.profile import ENV_KEY_OWNERS, OnboardProfile

_INFRA_DEFAULTS: dict[str, str] = {
    "INNGEST_EVENT_KEY": "dev",
    "INNGEST_DEV": "1",
    "INNGEST_API_BASE_URL": "http://localhost:8289",
}

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
    ("Tailscale", ["TAILSCALE_AUTH_KEY", "TAILSCALE_MACBOOK_IP"]),
]


def _read_existing(path: Path) -> dict[str, str]:
    pairs: dict[str, str] = {}
    if not path.exists():
        return pairs
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        pairs[key.strip()] = value.strip()
    return pairs


def _write_sectioned(path: Path, merged: dict[str, str]) -> None:
    lines: list[str] = []
    written_keys: set[str] = set()

    for section_name, section_keys in _SECTIONS:
        section_lines = [f"{key}={merged[key]}" for key in section_keys if merged.get(key)]
        written_keys.update(key for key in section_keys if merged.get(key))
        if section_lines:
            if lines:
                lines.append("")
            lines.append(f"# === {section_name} ===")
            lines.extend(section_lines)

    leftover = {key: value for key, value in merged.items() if key not in written_keys and value}
    if leftover:
        if lines:
            lines.append("")
        lines.append("# === Other ===")
        for key, value in sorted(leftover.items()):
            lines.append(f"{key}={value}")

    lines.append("")
    path.write_text("\n".join(lines))


def write_env(profile: OnboardProfile, path: Path) -> None:
    existing = _read_existing(path)
    _assert_generated_keys_have_owners(profile.keys)

    merged = {**existing, **profile.keys}
    for key, default in _INFRA_DEFAULTS.items():
        merged.setdefault(key, default)
    _assert_generated_keys_have_owners({key: merged[key] for key in _INFRA_DEFAULTS})

    _write_sectioned(path, merged)


def _assert_generated_keys_have_owners(keys: dict[str, str]) -> None:
    missing_owners = [key for key, value in keys.items() if value and key not in ENV_KEY_OWNERS]
    if missing_owners:
        raise ValueError(f"env keys missing owner category: {', '.join(sorted(missing_owners))}")


def _known_env_keys() -> set[str]:
    return {key for _, keys in _SECTIONS for key in keys} | set(_INFRA_DEFAULTS)
