"""``ergon start`` and ``ergon stop`` — bring the local dev stack up and down.

Thin wrappers around ``docker compose`` against the repo-root
``docker-compose.yml``. They exist so contributors don't need to memorise
the canonical incantation documented in the compose-file header —
``ergon doctor`` is the diagnostic counterpart.

Scope is intentionally minimal in v1:

* ``ergon start``  → ``docker compose up -d --wait`` (then prints URLs)
* ``ergon stop``   → ``docker compose down``

Optional flags (``--build``, ``--observability``, ``--logs``) and
companion commands (``ergon restart`` / ``ergon logs``) are deferred.
"""

import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

# Service URLs printed on a successful ``ergon start``. Kept in sync with
# the ``ports`` blocks in ``docker-compose.yml`` (host:container
# conventions documented in the compose-file header).
_SERVICE_URLS: tuple[tuple[str, str], ...] = (
    ("API", "http://localhost:9000"),
    ("Dashboard", "http://localhost:3001"),
    ("Inngest", "http://localhost:8289"),
    ("Postgres", "localhost:5433 (user=ergon, db=ergon)"),
)


def _find_compose_file(start: Path) -> Path | None:
    """Walk up from ``start`` looking for ``docker-compose.yml``.

    Returns the directory containing it (the resolved repo root) so
    ``docker compose`` can be invoked with ``cwd=<repo root>`` regardless
    of where the user ran ``ergon start`` from. Returns ``None`` if no
    compose file is found between ``start`` and the filesystem root.
    """
    for directory in (start, *start.parents):
        if (directory / "docker-compose.yml").is_file():
            return directory
    return None


def _check_docker_daemon() -> bool:
    """Return True iff the ``docker`` CLI is on PATH and the daemon is up.

    Mirrors ``_check_docker`` in ``ergon_cli.commands.doctor`` but kept
    private to this module: doctor's helper prints PASS/WARN messages,
    whereas ``ergon start`` wants a quiet predicate it can branch on
    before producing its own error message.
    """
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _print_url_summary() -> None:
    print("\nErgon dev stack is up.")
    width = max(len(label) for label, _ in _SERVICE_URLS)
    for label, url in _SERVICE_URLS:
        print(f"  {label:<{width}}  {url}")
    print("\nRun `ergon doctor` to verify connectivity.")


def handle_start(args: Namespace) -> int:
    """``ergon start`` — bring the dev stack up.

    Equivalent to ``docker compose up -d --wait`` from the repo root.
    Pre-flight: refuses if the docker daemon isn't reachable so the
    user gets a clear message instead of compose's default error.
    """
    del args  # no flags in the v1 surface

    repo_root = _find_compose_file(Path.cwd())
    if repo_root is None:
        print(
            "ergon start: could not find docker-compose.yml walking up from "
            f"{Path.cwd()}. Run `ergon start` from inside the ergon repo.",
            file=sys.stderr,
        )
        return 1

    if not _check_docker_daemon():
        print(
            "ergon start: Docker daemon is not running (or `docker` is not on "
            "PATH). Start Docker Desktop / your daemon and retry. Run "
            "`ergon doctor` for a full environment check.",
            file=sys.stderr,
        )
        return 1

    cmd = ["docker", "compose", "up", "-d", "--wait"]
    print(f"$ {' '.join(cmd)}  (cwd={repo_root})")
    try:
        result = subprocess.run(cmd, cwd=repo_root, check=False)
    except FileNotFoundError:
        print(
            "ergon start: `docker` was not found on PATH after the daemon "
            "check. Install Docker Desktop or the docker CLI and retry.",
            file=sys.stderr,
        )
        return 1

    if result.returncode != 0:
        print(
            f"\nergon start: docker compose exited with status "
            f"{result.returncode}. Check the output above and run "
            "`ergon doctor` for diagnostics.",
            file=sys.stderr,
        )
        return result.returncode

    _print_url_summary()
    return 0


def handle_stop(args: Namespace) -> int:
    """``ergon stop`` — tear the dev stack down via ``docker compose down``."""
    del args

    repo_root = _find_compose_file(Path.cwd())
    if repo_root is None:
        print(
            "ergon stop: could not find docker-compose.yml walking up from "
            f"{Path.cwd()}. Run `ergon stop` from inside the ergon repo.",
            file=sys.stderr,
        )
        return 1

    if shutil.which("docker") is None:
        print(
            "ergon stop: `docker` is not on PATH. Nothing to stop.",
            file=sys.stderr,
        )
        return 1

    cmd = ["docker", "compose", "down"]
    print(f"$ {' '.join(cmd)}  (cwd={repo_root})")
    try:
        result = subprocess.run(cmd, cwd=repo_root, check=False)
    except FileNotFoundError:
        print(
            "ergon stop: `docker` was not found on PATH. Nothing to stop.",
            file=sys.stderr,
        )
        return 1

    return result.returncode
