"""``ergon doctor`` — lightweight environment health check."""

import importlib
import shutil
import socket
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from urllib.parse import urlparse


def _ok(msg: str) -> None:
    print(f"  [PASS] {msg}")


def _warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


# ---------------------------------------------------------------------------
# Individual checks — each returns True when healthy.
# ---------------------------------------------------------------------------


def _check_python_version() -> bool:
    v = sys.version_info
    label = f"Python {v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= (3, 13):
        _ok(label)
        return True
    _fail(f"{label} — Ergon requires Python >= 3.13")
    return False


def _check_env_file() -> bool:
    path = Path.cwd() / ".env"
    if path.exists():
        _ok(f".env found at {path}")
        return True
    _warn(".env not found — run `ergon onboard` to create one")
    return False


def _check_docker() -> bool:
    docker = shutil.which("docker")
    if not docker:
        _warn("docker not found on PATH")
        return False
    try:
        result = subprocess.run(
            [docker, "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            _ok("Docker is running")
            return True
        _warn("Docker found but daemon is not running")
        return False
    except (subprocess.TimeoutExpired, OSError):
        _warn("Docker check timed out or failed")
        return False


def _check_tcp(host: str, port: int, label: str) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            _ok(f"{label} reachable at {host}:{port}")
            return True
    except OSError:
        _warn(f"{label} not reachable at {host}:{port}")
        return False


def _check_database() -> bool:
    try:
        # Deferred: avoid heavy import at CLI startup
        from ergon_core.core.settings import settings  # type: ignore[import-untyped]

        url = settings.database_url
        if url.startswith("sqlite"):
            _ok(f"Database configured (SQLite): {url}")
            return True

        if "@" in url:
            after_at = url.split("@", 1)[1]
            host_port = after_at.split("/", 1)[0]
            host, _, port_str = host_port.partition(":")
            port = int(port_str) if port_str else 5432
            return _check_tcp(host, port, "PostgreSQL")

        _warn(f"Cannot parse database URL: {url}")
        return False
    except (ImportError, OSError, ValueError) as exc:
        _warn(f"Cannot read database settings: {exc}")
        return False


def _check_inngest() -> bool:
    try:
        # Deferred: avoid heavy import at CLI startup
        from ergon_core.core.settings import settings  # type: ignore[import-untyped]

        base = settings.inngest_api_base_url
        parsed = urlparse(base)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8289
        return _check_tcp(host, port, "Inngest")
    except (ImportError, OSError, ValueError) as exc:
        _warn(f"Cannot read Inngest settings: {exc}")
        return False


def _check_packages() -> bool:
    required = ["ergon_core", "ergon_builtins", "ergon_cli"]
    missing = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        _ok(f"Core packages installed: {', '.join(required)}")
        return True
    _warn(f"Missing packages: {', '.join(missing)}")
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def handle_doctor(args: Namespace) -> int:
    print("\nErgon Doctor — checking your environment\n")

    checks = [
        _check_python_version,
        _check_env_file,
        _check_docker,
        _check_database,
        _check_inngest,
        _check_packages,
    ]

    all_ok = True
    for check in checks:
        if not check():
            all_ok = False

    print()
    if all_ok:
        print("All checks passed.")
    else:
        print("Some checks failed — see warnings above.")
    return 0 if all_ok else 1
