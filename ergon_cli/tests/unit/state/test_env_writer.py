"""Unit tests for the .env writer."""

from pathlib import Path

import pytest

from ergon_cli.domains.onboarding.env_writer import write_env
from ergon_cli.domains.onboarding.env_writer import _known_env_keys
from ergon_cli.domains.onboarding.profile import ENV_KEY_OWNERS, LLMProvider, OnboardProfile


class TestWriteEnv:
    def test_all_known_env_keys_have_owner_category(self) -> None:
        assert _known_env_keys() <= set(ENV_KEY_OWNERS)

    def test_creates_env_from_empty(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        profile = OnboardProfile(
            llm_providers=[LLMProvider.OPENAI],
            keys={"OPENAI_API_KEY": "sk-test-123"},
        )
        write_env(profile, env_path)

        content = env_path.read_text()
        assert "OPENAI_API_KEY=sk-test-123" in content
        # Infra defaults should always appear.
        assert "INNGEST_EVENT_KEY=dev" in content
        assert "INNGEST_DEV=1" in content

    def test_preserves_existing_unknown_keys(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("TAILSCALE_AUTH_KEY=hello\nOPENAI_API_KEY=old-key\n")

        profile = OnboardProfile(
            keys={"OPENAI_API_KEY": "new-key"},
        )
        write_env(profile, env_path)

        content = env_path.read_text()
        assert "OPENAI_API_KEY=new-key" in content
        assert "old-key" not in content
        assert "TAILSCALE_AUTH_KEY=hello" in content

    def test_rejects_written_keys_without_owner_category(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        profile = OnboardProfile(keys={"MY_CUSTOM_VAR": "hello"})

        with pytest.raises(ValueError, match="missing owner category"):
            write_env(profile, env_path)

    def test_preserves_existing_unknown_keys_without_owner_category(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("MY_CUSTOM_VAR=hello\n")

        write_env(OnboardProfile(), env_path)

        assert "MY_CUSTOM_VAR=hello" in env_path.read_text()

    def test_sections_are_labeled(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        profile = OnboardProfile(
            keys={
                "OPENAI_API_KEY": "sk-abc",
                "E2B_API_KEY": "e2b-xyz",
            },
        )
        write_env(profile, env_path)

        content = env_path.read_text()
        assert "# === LLM Provider Keys ===" in content
        assert "# === Sandbox ===" in content
        assert "# === Inngest ===" in content

    def test_empty_keys_not_written(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        profile = OnboardProfile(keys={"OPENAI_API_KEY": ""})
        write_env(profile, env_path)

        content = env_path.read_text()
        assert "OPENAI_API_KEY" not in content

    def test_merges_with_existing_env(self, tmp_path: Path) -> None:
        env_path = tmp_path / ".env"
        env_path.write_text("E2B_API_KEY=existing-e2b\nINNGEST_EVENT_KEY=production\n")

        profile = OnboardProfile(
            keys={"OPENAI_API_KEY": "sk-new"},
        )
        write_env(profile, env_path)

        content = env_path.read_text()
        assert "OPENAI_API_KEY=sk-new" in content
        assert "E2B_API_KEY=existing-e2b" in content
        # Existing Inngest value should be preserved (not overridden by default).
        assert "INNGEST_EVENT_KEY=production" in content


class TestWriteEnvIntegration:
    def test_full_profile_round_trip(self, tmp_path: Path) -> None:
        """A realistic profile produces a readable, parseable .env."""
        env_path = tmp_path / ".env"
        profile = OnboardProfile(
            environments=["gdpeval", "smoke-test"],
            llm_providers=[LLMProvider.OPENAI, LLMProvider.ANTHROPIC],
            training=True,
            keys={
                "OPENAI_API_KEY": "sk-openai",
                "ANTHROPIC_API_KEY": "sk-anthropic",
                "E2B_API_KEY": "e2b-key",
            },
        )
        write_env(profile, env_path)

        # Re-parse the output to verify it's valid dotenv format.
        lines = env_path.read_text().splitlines()
        parsed: dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key, _, value = stripped.partition("=")
            parsed[key] = value

        assert parsed["OPENAI_API_KEY"] == "sk-openai"
        assert parsed["ANTHROPIC_API_KEY"] == "sk-anthropic"
        assert parsed["E2B_API_KEY"] == "e2b-key"
        assert parsed["INNGEST_EVENT_KEY"] == "dev"
