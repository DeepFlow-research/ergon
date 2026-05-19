import importlib
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

from ergon_cli.domains.doctor.models import DoctorCheck, DoctorCommand, DoctorReport


def run_doctor_checks(command: DoctorCommand) -> DoctorReport:
    del command
    checks = (
        _check_python_version(),
        _check_env_file(),
        _check_docker(),
        _check_database(),
        _check_inngest(),
        _check_packages(),
    )
    return DoctorReport(checks=checks)


def _pass(message: str) -> DoctorCheck:
    return DoctorCheck(status="PASS", message=message)


def _warn(message: str) -> DoctorCheck:
    return DoctorCheck(status="WARN", message=message)


def _fail(message: str) -> DoctorCheck:
    return DoctorCheck(status="FAIL", message=message)


def _check_python_version() -> DoctorCheck:
    version = sys.version_info
    label = f"Python {version.major}.{version.minor}.{version.micro}"
    if (version.major, version.minor) >= (3, 13):
        return _pass(label)
    return _fail(f"{label} — Ergon requires Python >= 3.13")


def _check_env_file() -> DoctorCheck:
    path = Path.cwd() / ".env"
    if path.exists():
        return _pass(f".env found at {path}")
    return _warn(".env not found — run `ergon onboard` to create one")


def _check_docker() -> DoctorCheck:
    docker = shutil.which("docker")
    if not docker:
        return _warn("docker not found on PATH")
    try:
        result = subprocess.run(
            [docker, "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode == 0:
            return _pass("Docker is running")
        return _warn("Docker found but daemon is not running")
    except (subprocess.TimeoutExpired, OSError):
        return _warn("Docker check timed out or failed")


def _check_tcp(host: str, port: int, label: str) -> DoctorCheck:
    try:
        with socket.create_connection((host, port), timeout=3):
            return _pass(f"{label} reachable at {host}:{port}")
    except OSError:
        return _warn(f"{label} not reachable at {host}:{port}")


def _check_database() -> DoctorCheck:
    try:
        from ergon_core.core.shared.settings import settings  # type: ignore[import-untyped]

        url = settings.database_url
        if url.startswith("sqlite"):
            return _pass(f"Database configured (SQLite): {url}")

        if "@" in url:
            after_at = url.split("@", 1)[1]
            host_port = after_at.split("/", 1)[0]
            host, _, port_str = host_port.partition(":")
            port = int(port_str) if port_str else 5432
            return _check_tcp(host, port, "PostgreSQL")

        return _warn(f"Cannot parse database URL: {url}")
    except (ImportError, OSError, ValueError) as exc:
        return _warn(f"Cannot read database settings: {exc}")


def _check_inngest() -> DoctorCheck:
    try:
        from ergon_core.core.shared.settings import settings  # type: ignore[import-untyped]

        base = settings.inngest_api_base_url
        parsed = urlparse(base)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8289
        return _check_tcp(host, port, "Inngest")
    except (ImportError, OSError, ValueError) as exc:
        return _warn(f"Cannot read Inngest settings: {exc}")


def _check_packages() -> DoctorCheck:
    required = ["ergon_core", "ergon_builtins", "ergon_cli"]
    missing: list[str] = []
    for pkg in required:
        try:
            importlib.import_module(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return _pass(f"Core packages installed: {', '.join(required)}")
    return _warn(f"Missing packages: {', '.join(missing)}")
