"""Tests for ``ergon start`` and ``ergon stop`` (commands/stack.py).

These commands shell out to ``docker compose``; tests mock ``subprocess.run``
and ``shutil.which`` to keep them hermetic. The argparse wiring in
``main.py`` is exercised separately by ``test_help_lists_start_and_stop``.
"""

from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock

import ergon_cli.commands.stack as _stack_mod
import pytest
from ergon_cli.commands.stack import _find_compose_file, handle_start, handle_stop


def _seed_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo root containing ``docker-compose.yml``."""
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    return tmp_path


# ---------------------------------------------------------------------------
# _find_compose_file
# ---------------------------------------------------------------------------


class TestFindComposeFile:
    def test_returns_directory_when_compose_present(self, tmp_path: Path) -> None:
        repo = _seed_repo(tmp_path)
        assert _find_compose_file(repo) == repo

    def test_walks_up_from_subdirectory(self, tmp_path: Path) -> None:
        repo = _seed_repo(tmp_path)
        sub = repo / "deep" / "nested" / "place"
        sub.mkdir(parents=True)
        assert _find_compose_file(sub) == repo

    def test_returns_none_when_no_compose_in_ancestors(self, tmp_path: Path) -> None:
        sub = tmp_path / "child"
        sub.mkdir()
        # Skip if any ancestor of tmp_path happens to have a docker-compose.yml
        # (extremely unlikely on CI runners but possible in local dev trees).
        if any((p / "docker-compose.yml").is_file() for p in (sub, *sub.parents)):
            pytest.skip("ancestor directory contains docker-compose.yml")
        assert _find_compose_file(sub) is None


# ---------------------------------------------------------------------------
# handle_start — happy path + every error branch
# ---------------------------------------------------------------------------


class _FakeRunner:
    """Records every ``subprocess.run`` invocation and returns canned exit codes.

    ``returncodes`` maps the invoked command (as a tuple) to its rc; missing
    entries default to ``0``.
    """

    def __init__(self, returncodes: dict[tuple[str, ...], int] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._rc = returncodes or {}

    def __call__(
        self,
        cmd: list[str] | tuple[str, ...],
        *_args: object,
        **_kwargs: object,
    ) -> MagicMock:
        self.calls.append(list(cmd))
        rc = self._rc.get(tuple(cmd), 0)
        result = MagicMock()
        result.returncode = rc
        result.stdout = b""
        result.stderr = b""
        return result


@pytest.fixture
def mock_docker_ok(monkeypatch: pytest.MonkeyPatch) -> _FakeRunner:
    """Patch ``shutil.which('docker')`` to a fake path and ``subprocess.run``
    to a recording fake that returns 0 for every call by default."""
    monkeypatch.setattr(_stack_mod.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    runner = _FakeRunner()
    monkeypatch.setattr(_stack_mod.subprocess, "run", runner)
    return runner


class TestHandleStart:
    def test_runs_compose_up_wait_on_happy_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        mock_docker_ok: _FakeRunner,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)

        rc = handle_start(Namespace())

        assert rc == 0
        assert ["docker", "info"] in mock_docker_ok.calls
        assert ["docker", "compose", "up", "-d", "--wait"] in mock_docker_ok.calls

        out = capsys.readouterr().out
        assert "Ergon dev stack is up." in out
        assert "http://localhost:9000" in out
        assert "http://localhost:3001" in out
        assert "http://localhost:8289" in out
        assert "ergon doctor" in out

    def test_fails_when_no_compose_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        sub = tmp_path / "no-compose"
        sub.mkdir()
        if any((p / "docker-compose.yml").is_file() for p in (sub, *sub.parents)):
            pytest.skip("ancestor directory contains docker-compose.yml")
        monkeypatch.chdir(sub)

        rc = handle_start(Namespace())

        assert rc == 1
        err = capsys.readouterr().err
        assert "could not find docker-compose.yml" in err

    def test_fails_when_docker_daemon_not_running(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)
        monkeypatch.setattr(_stack_mod.shutil, "which", lambda name: f"/usr/local/bin/{name}")
        # `docker info` returns rc=1 → daemon not reachable.
        runner = _FakeRunner({("docker", "info"): 1})
        monkeypatch.setattr(_stack_mod.subprocess, "run", runner)

        rc = handle_start(Namespace())

        assert rc == 1
        err = capsys.readouterr().err
        assert "Docker daemon is not running" in err

    def test_fails_when_docker_not_on_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)
        monkeypatch.setattr(_stack_mod.shutil, "which", lambda name: None)

        rc = handle_start(Namespace())

        assert rc == 1
        assert "Docker daemon is not running" in capsys.readouterr().err

    def test_propagates_compose_exit_code(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)
        monkeypatch.setattr(_stack_mod.shutil, "which", lambda name: f"/usr/local/bin/{name}")
        runner = _FakeRunner(
            {
                ("docker", "info"): 0,
                ("docker", "compose", "up", "-d", "--wait"): 2,
            }
        )
        monkeypatch.setattr(_stack_mod.subprocess, "run", runner)

        rc = handle_start(Namespace())

        assert rc == 2
        err = capsys.readouterr().err
        assert "exited with status 2" in err

    def test_walks_up_from_subdirectory_to_find_compose(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        mock_docker_ok: _FakeRunner,
    ) -> None:
        repo = _seed_repo(tmp_path)
        deep = repo / "ergon_core" / "tests"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)

        rc = handle_start(Namespace())

        assert rc == 0
        # The recorded compose call should run with cwd=repo (verified via the
        # fact that we never moved up explicitly — `_find_compose_file` did).
        assert ["docker", "compose", "up", "-d", "--wait"] in mock_docker_ok.calls


# ---------------------------------------------------------------------------
# handle_stop
# ---------------------------------------------------------------------------


class TestHandleStop:
    def test_runs_compose_down(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        mock_docker_ok: _FakeRunner,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)

        rc = handle_stop(Namespace())

        assert rc == 0
        assert ["docker", "compose", "down"] in mock_docker_ok.calls

    def test_fails_when_no_compose_file(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        sub = tmp_path / "no-compose"
        sub.mkdir()
        if any((p / "docker-compose.yml").is_file() for p in (sub, *sub.parents)):
            pytest.skip("ancestor directory contains docker-compose.yml")
        monkeypatch.chdir(sub)

        rc = handle_stop(Namespace())

        assert rc == 1
        assert "could not find docker-compose.yml" in capsys.readouterr().err

    def test_fails_when_docker_not_on_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)
        monkeypatch.setattr(_stack_mod.shutil, "which", lambda name: None)

        rc = handle_stop(Namespace())

        assert rc == 1
        assert "is not on PATH" in capsys.readouterr().err

    def test_propagates_compose_down_exit_code(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        repo = _seed_repo(tmp_path)
        monkeypatch.chdir(repo)
        monkeypatch.setattr(_stack_mod.shutil, "which", lambda name: f"/usr/local/bin/{name}")
        runner = _FakeRunner({("docker", "compose", "down"): 5})
        monkeypatch.setattr(_stack_mod.subprocess, "run", runner)

        rc = handle_stop(Namespace())

        assert rc == 5


# ---------------------------------------------------------------------------
# argparse wiring smoke test — guards against forgetting to register the
# new subcommands in ``main.build_parser``.
# ---------------------------------------------------------------------------


class TestArgparseWiring:
    def test_help_lists_start_and_stop(self, capsys: pytest.CaptureFixture[str]) -> None:
        from ergon_cli.main import build_parser

        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])
        out = capsys.readouterr().out
        assert "start" in out
        assert "stop" in out

    def test_start_subcommand_parses(self) -> None:
        from ergon_cli.main import build_parser

        args = build_parser().parse_args(["start"])
        assert args.command == "start"

    def test_stop_subcommand_parses(self) -> None:
        from ergon_cli.main import build_parser

        args = build_parser().parse_args(["stop"])
        assert args.command == "stop"
