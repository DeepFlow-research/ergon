"""Tests for ``ergon benchmark setup <slug>`` CLI command."""

import json
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


class _FakeBuildInfo:
    """Stand-in for ``e2b.template.types.BuildInfo``."""

    def __init__(self, template_id: str = "tmpl_test123", build_id: str = "build_test") -> None:
        self.template_id = template_id
        self.build_id = build_id
        self.name = "ergon-minif2f-v1"
        self.alias = "ergon-minif2f-v1"
        self.tags: list[str] = []


def _patch_sdk(
    monkeypatch: pytest.MonkeyPatch,
    *,
    build_info: _FakeBuildInfo | None = None,
    raise_on_build: Exception | None = None,
) -> MagicMock:
    """Patch ``e2b.Template`` so ``setup_benchmark`` never hits the network."""

    # Builder returned from from_dockerfile()/set_start_cmd() — chainable MagicMock.
    builder = MagicMock()
    builder.from_dockerfile.return_value = builder
    builder.set_start_cmd.return_value = builder

    # `Template(...)` call returns the builder; `Template.build(...)` returns BuildInfo.
    fake_template_cls = MagicMock()
    fake_template_cls.return_value = builder
    if raise_on_build is not None:
        fake_template_cls.build.side_effect = raise_on_build
    else:
        fake_template_cls.build.return_value = build_info or _FakeBuildInfo()

    import e2b

    monkeypatch.setattr(e2b, "Template", fake_template_cls)
    # Also patch the already-imported name in the benchmark module.
    import ergon_cli.commands.benchmark as _bench_mod

    monkeypatch.setattr(_bench_mod, "Template", fake_template_cls)
    return fake_template_cls


# ---------------------------------------------------------------------------
# 1 & 2. Error scenarios — each checks both exit code and stderr message
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "setup_env,args_kwargs,expected_message",
    [
        (
            "api_key_unset",
            {},
            "E2B_API_KEY",
        ),
        (
            "unknown_slug",
            {"slug": "nonexistent"},
            None,
        ),
    ],
    ids=["api_key_unset", "unknown_slug"],
)
def test_error_scenarios(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    setup_env: str,
    args_kwargs: dict,
    expected_message: str | None,
) -> None:
    if setup_env == "api_key_unset":
        from ergon_core.core.settings import settings

        monkeypatch.setattr(settings, "e2b_api_key", "")
    else:
        monkeypatch.setenv("E2B_API_KEY", "test-key")

    rc = setup_benchmark(_make_args(**args_kwargs))
    assert rc != 0

    if expected_message is not None:
        captured = capsys.readouterr()
        assert expected_message in captured.err


# ---------------------------------------------------------------------------
# 3. Idempotency — skips build when already registered
# ---------------------------------------------------------------------------


def test_idempotent_skip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    # ``settings`` is a module-level singleton whose ``e2b_api_key`` was
    # cached at import time — ``setenv`` alone doesn't propagate to it.
    # Patch the attribute directly so these tests pass regardless of xdist
    # worker import ordering.
    from ergon_core.core.settings import settings

    monkeypatch.setattr(settings, "e2b_api_key", "test-key")

    registry = tmp_path / "sandbox_templates.json"
    registry.write_text(
        json.dumps({"minif2f": {"template_id": "abc123", "template_name": "ergon-minif2f-v1"}})
    )

    rc = setup_benchmark(_make_args())
    assert rc == 0


# ---------------------------------------------------------------------------
# 4. Happy path — full build + persist
# ---------------------------------------------------------------------------


def test_happy_path_creates_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    # ``settings`` is a module-level singleton whose ``e2b_api_key`` was
    # cached at import time — ``setenv`` alone doesn't propagate to it.
    # Patch the attribute directly so these tests pass regardless of xdist
    # worker import ordering.
    from ergon_core.core.settings import settings

    monkeypatch.setattr(settings, "e2b_api_key", "test-key")
    fake = _patch_sdk(monkeypatch)

    rc = setup_benchmark(_make_args())
    assert rc == 0

    fake.build.assert_called_once()

    registry = tmp_path / "sandbox_templates.json"
    assert registry.exists()
    data = json.loads(registry.read_text())
    assert "minif2f" in data
    assert data["minif2f"]["template_id"] == "tmpl_test123"
    assert data["minif2f"]["template_name"] == "ergon-minif2f-v1"
    assert data["minif2f"]["build_id"] == "build_test"
    assert "built_at" in data["minif2f"]


def test_force_rebuild_overwrites(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    # ``settings`` is a module-level singleton whose ``e2b_api_key`` was
    # cached at import time — ``setenv`` alone doesn't propagate to it.
    # Patch the attribute directly so these tests pass regardless of xdist
    # worker import ordering.
    from ergon_core.core.settings import settings

    monkeypatch.setattr(settings, "e2b_api_key", "test-key")
    _patch_sdk(monkeypatch)

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
# 5. Build failure propagates
# ---------------------------------------------------------------------------


def test_build_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    # ``settings`` is a module-level singleton whose ``e2b_api_key`` was
    # cached at import time — ``setenv`` alone doesn't propagate to it.
    # Patch the attribute directly so these tests pass regardless of xdist
    # worker import ordering.
    from ergon_core.core.settings import settings

    monkeypatch.setattr(settings, "e2b_api_key", "test-key")
    _patch_sdk(monkeypatch, raise_on_build=RuntimeError("simulated build failure"))

    rc = setup_benchmark(_make_args())
    assert rc != 0
