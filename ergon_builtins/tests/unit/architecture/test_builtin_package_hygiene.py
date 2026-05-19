"""Package hygiene checks for library-tier built-ins examples."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
BUILTINS_SRC = ROOT / "ergon_builtins" / "ergon_builtins"


def test_no_generated_python_artifacts_in_builtins_source() -> None:
    tracked_files = subprocess.run(
        ["git", "ls-files", "ergon_builtins/ergon_builtins"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    offenders = [path for path in tracked_files if "/__pycache__/" in path or path.endswith(".pyc")]

    assert offenders == []


def test_no_stray_editor_files_in_builtins_source() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in BUILTINS_SRC.rglob("*")
        if path.name == "Untitled"
    ]

    assert offenders == []


def test_cloud_passthrough_module_stays_deleted() -> None:
    assert not (BUILTINS_SRC / "models" / "cloud_passthrough.py").exists()
