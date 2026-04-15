"""Tests for ``ergon benchmark setup <slug>`` CLI command."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ergon_cli.commands.benchmark import setup_benchmark


def _make_args(slug: str = "minif2f", *, force: bool = False):
    """Return a minimal argparse-like Namespace."""
    ns = MagicMock()
    ns.slug = slug
    ns.force = force
    return ns


# ---------------------------------------------------------------------------
# 1. E2B CLI not installed
# ---------------------------------------------------------------------------


def test_fails_when_e2b_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    rc = setup_benchmark(_make_args())
    assert rc != 0


def test_error_message_mentions_install_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: None)
    setup_benchmark(_make_args())
    captured = capsys.readouterr()
    assert "https://e2b.dev/docs/cli" in captured.err


# ---------------------------------------------------------------------------
# 2. E2B_API_KEY not set
# ---------------------------------------------------------------------------


def test_fails_when_api_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    rc = setup_benchmark(_make_args())
    assert rc != 0


def test_error_message_mentions_api_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    setup_benchmark(_make_args())
    captured = capsys.readouterr()
    assert "E2B_API_KEY" in captured.err


# ---------------------------------------------------------------------------
# 3. Unknown slug
# ---------------------------------------------------------------------------


def test_fails_for_unknown_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    rc = setup_benchmark(_make_args(slug="nonexistent"))
    assert rc != 0


# ---------------------------------------------------------------------------
# 4. Idempotency — skips build when already registered
# ---------------------------------------------------------------------------


def test_idempotent_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))

    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(
        json.dumps({"minif2f": {"template_id": "abc123", "template_name": "ergon-minif2f-v1"}})
    )

    rc = setup_benchmark(_make_args())
    assert rc == 0


# ---------------------------------------------------------------------------
# 5. Happy path — full build + persist
# ---------------------------------------------------------------------------


def _fake_e2b_build(cmd, *, cwd=None, **_kwargs):  # noqa: ANN001, ANN003
    """Simulate ``e2b template build`` by writing an ``e2b.toml``."""
    if cwd is not None:
        e2b_toml = Path(cwd) / "e2b.toml"
        e2b_toml.write_text(
            'template_id = "tmpl_test123"\n'
            'template_name = "ergon-minif2f-v1"\n'
            'start_cmd = "/bin/bash"\n'
        )
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 0
    return result


def test_happy_path_creates_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("ergon_cli.commands.benchmark.subprocess.run", _fake_e2b_build)

    rc = setup_benchmark(_make_args())
    assert rc == 0

    registry = tmp_path / "sandbox_templates.json"
    assert registry.exists()
    data = json.loads(registry.read_text())
    assert "minif2f" in data
    assert data["minif2f"]["template_id"] == "tmpl_test123"
    assert data["minif2f"]["template_name"] == "ergon-minif2f-v1"
    assert "built_at" in data["minif2f"]


def test_force_rebuild_overwrites(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("ergon_cli.commands.benchmark.subprocess.run", _fake_e2b_build)

    # Pre-populate with old entry
    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(
        json.dumps({"minif2f": {"template_id": "old_id", "template_name": "ergon-minif2f-v1"}})
    )

    rc = setup_benchmark(_make_args(force=True))
    assert rc == 0

    data = json.loads(registry.read_text())
    assert data["minif2f"]["template_id"] == "tmpl_test123"


# ---------------------------------------------------------------------------
# 6. Build failure propagates
# ---------------------------------------------------------------------------


def _fake_e2b_build_failure(cmd, *, cwd=None, **_kwargs):  # noqa: ANN001, ANN003
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = 1
    return result


def test_build_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/local/bin/e2b")
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("ergon_cli.commands.benchmark.subprocess.run", _fake_e2b_build_failure)

    rc = setup_benchmark(_make_args())
    assert rc != 0
