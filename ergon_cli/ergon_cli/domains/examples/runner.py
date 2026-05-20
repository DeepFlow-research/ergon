import os
import subprocess
import sys
from pathlib import Path

from ergon_cli.domains.examples.models import ExampleCommand, ExampleDefinition


class ExampleRunError(RuntimeError):
    """Raised when an example script cannot be run from the current checkout."""


def run_example_script(example: ExampleDefinition, command: ExampleCommand) -> int:
    repo_root = _repo_root(example.script_path)
    script_path = repo_root / example.script_path
    process = subprocess.run(
        [sys.executable, str(script_path), *_script_args(command)],
        cwd=repo_root,
        env=os.environ.copy(),
    )
    return process.returncode


def _script_args(command: ExampleCommand) -> list[str]:
    args: list[str] = []
    if command.limit is not None:
        args.extend(["--limit", str(command.limit)])
    if command.model_target is not None:
        args.extend(["--model-target", command.model_target])
    else:
        if command.base_url is not None:
            args.extend(["--base-url", command.base_url])
        if command.model is not None:
            args.extend(["--model", command.model])
    if command.max_iterations is not None:
        args.extend(["--max-iterations", str(command.max_iterations)])
    return args


def _repo_root(script_path: str) -> Path:
    configured = os.environ.get("ERGON_REPO_ROOT")
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured).resolve())
    cwd = Path.cwd().resolve()
    candidates.append(cwd)
    candidates.extend(cwd.parents)

    for candidate in candidates:
        if (candidate / script_path).is_file():
            return candidate

    raise ExampleRunError(
        "Could not find the example script. Run this command from an Ergon source "
        "checkout, or set ERGON_REPO_ROOT to the repository root."
    )
