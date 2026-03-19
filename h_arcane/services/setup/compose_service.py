"""Docker Compose helpers for local development workflows."""

from __future__ import annotations

import subprocess

from h_arcane.services.setup.common import project_root


class ComposeService:
    """Thin wrapper around `docker compose` for common local operations."""

    def __init__(self):
        self._cwd = project_root()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", *args],
            cwd=self._cwd,
            text=True,
            capture_output=True,
            check=False,
        )

    def up(self, services: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        args = ["up", "-d", *(services or [])]
        return self._run(args)

    def down(self) -> subprocess.CompletedProcess[str]:
        return self._run(["down"])

    def logs(
        self,
        services: list[str] | None = None,
        tail: int = 100,
        follow: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        args = ["logs", "--tail", str(tail)]
        if follow:
            args.append("--follow")
        args.extend(services or [])
        return self._run(args)

    def running_services(self) -> set[str]:
        result = self._run(["ps", "--services", "--status", "running"])
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
