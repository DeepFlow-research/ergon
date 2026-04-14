"""Install pip extras via ``uv``."""

import shutil
import subprocess


def install_extras(extras: list[str], *, dry_run: bool = False) -> None:
    """Run ``uv pip install`` for each extra spec."""
    if not extras:
        return

    uv = shutil.which("uv")
    if not uv:
        print("  Error: uv not found on PATH. Install it: https://docs.astral.sh/uv/")
        raise SystemExit(1)

    cmd = [uv, "pip", "install", *extras]

    if dry_run:
        print(f"  Would run: {' '.join(cmd)}")
        return

    print(f"  Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)  # noqa: S603
