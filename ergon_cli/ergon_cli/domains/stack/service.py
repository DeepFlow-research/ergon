import shutil
import subprocess
from pathlib import Path

from ergon_cli.domains.stack.models import StackCommand, StackResult
from ergon_cli.shared import exit_codes

SERVICE_URLS: tuple[tuple[str, str], ...] = (
    ("Dashboard", "http://localhost:3001"),
    ("API", "http://localhost:9000"),
    ("Inngest", "http://localhost:8289"),
    ("Postgres", "postgresql://ergon:ergon_dev@localhost:5433/ergon"),
)


def run_stack_command(command: StackCommand) -> StackResult:
    if command.action == "start":
        return start_stack(command)
    return stop_stack(command)


def find_compose_file(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / "docker-compose.yml").is_file():
            return directory
    return None


def check_docker_daemon() -> bool:
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


def start_stack(command: StackCommand) -> StackResult:
    repo_root = find_compose_file(command.cwd)
    if repo_root is None:
        return StackResult(
            exit_code=exit_codes.RUNTIME_ERROR,
            stderr=(
                "ergon start: could not find docker-compose.yml walking up from "
                f"{command.cwd}. Run `ergon start` from inside the ergon repo.",
            ),
        )

    if not check_docker_daemon():
        return StackResult(
            exit_code=exit_codes.RUNTIME_ERROR,
            stderr=(
                "ergon start: Docker daemon is not running (or `docker` is not on "
                "PATH). Start Docker Desktop / your daemon and retry. Run "
                "`ergon doctor` for a full environment check.",
            ),
        )

    cmd = ["docker", "compose", "up", "-d", "--wait"]
    stdout = [f"$ {' '.join(cmd)}  (cwd={repo_root})"]
    try:
        result = subprocess.run(cmd, cwd=repo_root, check=False)
    except FileNotFoundError:
        return StackResult(
            exit_code=exit_codes.RUNTIME_ERROR,
            stderr=(
                "ergon start: `docker` was not found on PATH after the daemon "
                "check. Install Docker Desktop or the docker CLI and retry.",
            ),
        )

    if result.returncode != 0:
        return StackResult(
            exit_code=result.returncode,
            stdout=tuple(stdout),
            stderr=(
                f"\nergon start: docker compose exited with status {result.returncode}. "
                "Check the output above and run `ergon doctor` for diagnostics.",
            ),
        )

    stdout.extend(["", "Ergon dev stack is up.", "", "Services"])
    width = max(len(label) for label, _ in SERVICE_URLS)
    stdout.extend(f"  {label:<{width}}  {url}" for label, url in SERVICE_URLS)
    stdout.extend(["", "Run `ergon doctor` to verify connectivity."])
    return StackResult(exit_code=exit_codes.OK, stdout=tuple(stdout))


def stop_stack(command: StackCommand) -> StackResult:
    repo_root = find_compose_file(command.cwd)
    if repo_root is None:
        return StackResult(
            exit_code=exit_codes.RUNTIME_ERROR,
            stderr=(
                "ergon stop: could not find docker-compose.yml walking up from "
                f"{command.cwd}. Run `ergon stop` from inside the ergon repo.",
            ),
        )

    if shutil.which("docker") is None:
        return StackResult(
            exit_code=exit_codes.RUNTIME_ERROR,
            stderr=("ergon stop: `docker` is not on PATH. Nothing to stop.",),
        )

    cmd = ["docker", "compose", "down"]
    stdout = [f"$ {' '.join(cmd)}  (cwd={repo_root})"]
    try:
        result = subprocess.run(cmd, cwd=repo_root, check=False)
    except FileNotFoundError:
        return StackResult(
            exit_code=exit_codes.RUNTIME_ERROR,
            stderr=("ergon stop: `docker` was not found on PATH. Nothing to stop.",),
        )
    return StackResult(exit_code=result.returncode, stdout=tuple(stdout))
