"""Integration test for the onboard wizard with monkeypatched I/O."""

from pathlib import Path
from unittest.mock import patch

from ergon_cli.commands.onboard import handle_onboard


class _FakeArgs:
    pass


class TestOnboardWizard:
    def test_minimal_flow_cloud_only(self, tmp_path: Path, monkeypatch: object) -> None:
        """User picks smoke-test, OpenAI, no training.

        Sorted benchmark order (9 slugs):
          1. delegation-smoke
          2. gdpeval
          3. minif2f
          4. researchrubrics
          5. researchrubrics-ablated
          6. researchrubrics-smoke
          7. researchrubrics-vanilla
          8. smoke-test
          9. swebench-verified
        """
        env_path = tmp_path / ".env"
        monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

        # Sequence of user inputs the wizard will consume:
        #   1. select_multiple (benchmarks): "8" = smoke-test
        #   2. select_multiple (LLM providers): "1" = openai
        #   3. confirm (training): "n"
        #   4. ask_secret (OPENAI_API_KEY): "sk-test"
        #   5. ask_secret (E2B_API_KEY): "e2b-test"
        inputs = iter(["8", "1", "n", "sk-test", "e2b-test"])

        with (
            patch("builtins.input", side_effect=lambda *_a, **_kw: next(inputs)),
            patch("getpass.getpass", side_effect=lambda *_a, **_kw: next(inputs)),
            patch("ergon_cli.commands.onboard.install_extras"),
        ):
            result = handle_onboard(_FakeArgs())  # type: ignore[arg-type]

        assert result == 0
        assert env_path.exists()
        content = env_path.read_text()
        assert "OPENAI_API_KEY=sk-test" in content
        assert "E2B_API_KEY=e2b-test" in content

    def test_training_with_remote_gpu(self, tmp_path: Path, monkeypatch: object) -> None:
        """User picks minif2f, Anthropic, training with Shadeform."""
        env_path = tmp_path / ".env"
        monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

        # Sequence:
        #   1. benchmarks: "3" = minif2f
        #   2. LLM providers: "2" = anthropic
        #   3. training: "y"
        #   4. local GPU: "n"
        #   5. cloud provider: "1" = shadeform
        #   6. ask_secret (ANTHROPIC_API_KEY): "sk-ant"
        #   7. ask_secret (E2B_API_KEY): "e2b-key"
        #   8. ask_secret (SHADEFORM_API_KEY): "sf-key"
        inputs = iter(["3", "2", "y", "n", "1", "sk-ant", "e2b-key", "sf-key"])

        with (
            patch("builtins.input", side_effect=lambda *_a, **_kw: next(inputs)),
            patch("getpass.getpass", side_effect=lambda *_a, **_kw: next(inputs)),
            patch("ergon_cli.commands.onboard.install_extras") as mock_install,
        ):
            result = handle_onboard(_FakeArgs())  # type: ignore[arg-type]

        assert result == 0
        content = env_path.read_text()
        assert "ANTHROPIC_API_KEY=sk-ant" in content
        assert "E2B_API_KEY=e2b-key" in content
        assert "SHADEFORM_API_KEY=sf-key" in content

        extras = mock_install.call_args[0][0]
        assert "ergon-infra[training]" in extras
        assert "ergon-infra[skypilot]" in extras

    def test_no_keys_needed(self, tmp_path: Path, monkeypatch: object) -> None:
        """User picks researchrubrics (optional Exa only), OpenRouter, no training."""
        env_path = tmp_path / ".env"
        monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]

        inputs = iter(["4", "4", "n", "or-key", "exa-key"])

        with (
            patch("builtins.input", side_effect=lambda *_a, **_kw: next(inputs)),
            patch("getpass.getpass", side_effect=lambda *_a, **_kw: next(inputs)),
            patch("ergon_cli.commands.onboard.install_extras") as mock_install,
        ):
            result = handle_onboard(_FakeArgs())  # type: ignore[arg-type]

        assert result == 0
        content = env_path.read_text()
        assert "OPENROUTER_API_KEY=or-key" in content
        assert "EXA_API_KEY=exa-key" in content
        extras = mock_install.call_args[0][0]
        assert "ergon-builtins[data]" in extras
