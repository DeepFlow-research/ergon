"""MiniF2F data loading using the Task facade.

This module provides functions to load MiniF2F (formal mathematics) problems:
- load_minif2f_task(): Load a single problem as a Task object
- load_minif2f_to_database(): Bulk load problems using the Task persistence layer
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from h_arcane.benchmarks.common.loader import load_benchmark_to_database
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
from h_arcane.benchmarks.minif2f.schemas import MiniF2FProblem
from h_arcane.core.settings import settings
from h_arcane.core.task import Task

if TYPE_CHECKING:
    from h_arcane.core.worker import BaseWorker


def get_data_dir() -> Path:
    """Get the data directory path from settings."""
    return settings.data_dir


MINIF2F_REPO = "https://github.com/facebookresearch/miniF2F"


def download_minif2f(data_dir: Path | None = None) -> Path:
    """Clone MiniF2F repo if not exists.

    Args:
        data_dir: Base data directory (defaults to project data/ directory)

    Returns:
        Path to minif2f directory
    """
    if data_dir is None:
        data_dir = get_data_dir()

    minif2f_dir = data_dir / "raw" / "minif2f"
    if not minif2f_dir.exists():
        print(f"Cloning MiniF2F repository to {minif2f_dir}...", file=sys.stderr)
        subprocess.run(
            ["git", "clone", MINIF2F_REPO, str(minif2f_dir)],
            check=True,
        )
        print("   Cloned MiniF2F repository", file=sys.stderr)
    else:
        print(f"   MiniF2F repository already exists at {minif2f_dir}", file=sys.stderr)

    return minif2f_dir


def extract_problem_from_lean(theorem_content: str, problem_id: str, split: str) -> MiniF2FProblem:
    """Extract problem statement and ground truth proof from a single theorem block.

    Args:
        theorem_content: Content of a single theorem (from theorem ... end)
        problem_id: Problem identifier (theorem name)
        split: Dataset split ("valid" or "test")

    Returns:
        MiniF2FProblem with parsed statement and proof
    """
    # Extract theorem statement (everything up to :=)
    lines = theorem_content.split("\n")
    statement_lines = []
    for line in lines:
        statement_lines.append(line)
        if ":=" in line:
            break

    problem_statement = "\n".join(statement_lines).strip()

    # The full theorem content is the ground truth proof (may contain 'sorry' for unsolved)
    ground_truth_proof = theorem_content.strip()

    return MiniF2FProblem(
        problem_id=problem_id,
        problem_statement=problem_statement,
        ground_truth_proof=ground_truth_proof,
        split=split,
        lean_file_path=None,
    )


def parse_lean_problems(minif2f_dir: Path, limit: int | None = None) -> list[MiniF2FProblem]:
    """Parse Lean files from lean/src/valid.lean and lean/src/test.lean.

    MiniF2F repo structure: single files containing multiple theorems.
    Each theorem starts with 'theorem <name>' and ends with 'end'.

    Args:
        minif2f_dir: Path to MiniF2F repository root
        limit: Optional limit on number of problems to load

    Returns:
        List of MiniF2FProblem objects
    """
    problems: list[MiniF2FProblem] = []

    for split in ["valid", "test"]:
        lean_file = minif2f_dir / "lean" / "src" / f"{split}.lean"
        if not lean_file.exists():
            print(f"   File not found: {lean_file}", file=sys.stderr)
            continue

        try:
            content = lean_file.read_text(encoding="utf-8")

            # Extract individual theorems using regex
            # Pattern: theorem <name> ... end
            # We need to match nested 'begin'/'end' blocks correctly
            theorem_pattern = r"theorem\s+(\w+)\s+.*?(?=\n\s*theorem|\Z)"
            matches = re.finditer(theorem_pattern, content, re.DOTALL)

            for match in matches:
                if limit and len(problems) >= limit:
                    break

                theorem_name = match.group(1)
                theorem_content = match.group(0).strip()

                # Extract just the theorem block (from 'theorem' to matching 'end')
                # Find the matching 'end' for this theorem
                lines = theorem_content.split("\n")
                depth = 0
                end_idx = len(lines)
                for i, line in enumerate(lines):
                    if "begin" in line:
                        depth += 1
                    elif "end" in line:
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break

                theorem_block = "\n".join(lines[:end_idx])

                try:
                    problem = extract_problem_from_lean(theorem_block, theorem_name, split)
                    problem.lean_file_path = lean_file
                    problems.append(problem)
                except Exception as e:
                    print(
                        f"   Failed to parse theorem {theorem_name}: {e}",
                        file=sys.stderr,
                    )
                    continue

            print(
                f"   Found {len([m for m in re.finditer(theorem_pattern, content, re.DOTALL)])} theorems in {split}.lean",
                file=sys.stderr,
            )

        except Exception as e:
            print(f"   Failed to read {lean_file}: {e}", file=sys.stderr)
            continue

        if limit and len(problems) >= limit:
            break

    print(f"   Parsed {len(problems)} problems", file=sys.stderr)
    return problems


def _get_problem_by_id(problem_id: str, problems: list[MiniF2FProblem]) -> MiniF2FProblem | None:
    """Find a problem by its ID in a list of problems."""
    for problem in problems:
        if problem.problem_id == problem_id:
            return problem
    return None


def load_minif2f_task(
    problem_id: str,
    worker: "BaseWorker",
    data_dir: Path | None = None,
) -> Task:
    """
    Load a single MiniF2F problem as a Task object.

    This function returns a Task that is NOT yet persisted - the caller
    decides whether to execute it immediately or persist it first.

    Args:
        problem_id: The MiniF2F problem ID (theorem name, e.g., "amc12a_2008_p25")
        worker: The worker to assign to this task
        data_dir: Optional data directory (will clone repo if needed)

    Returns:
        A Task object ready for execution or persistence

    Example:
        >>> worker = ReActWorker(model="gpt-4o", config=MINIF2F_CONFIG)
        >>> task = load_minif2f_task("amc12a_2008_p25", worker)
        >>> result = await execute_task(task)
    """
    # Download/clone repository if needed
    minif2f_dir = download_minif2f(data_dir)

    # Parse all problems (we need to find the specific one)
    problems = parse_lean_problems(minif2f_dir)

    problem = _get_problem_by_id(problem_id, problems)
    if problem is None:
        raise ValueError(f"Problem {problem_id} not found in MiniF2F dataset")

    # Create rubric evaluator
    rubric = MiniF2FRubric(
        benchmark="minif2f",
        max_score=1.0,
        partial_credit_for_syntax=0.2,
    )

    # MiniF2F has no input files - just the problem statement
    return Task(
        name=problem.problem_id,
        description=problem.problem_statement,
        assigned_to=worker,
        resources=[],  # MiniF2F problems don't have input files
        evaluator=rubric,
    )


def _minif2f_item_to_task(problem: MiniF2FProblem, worker: "BaseWorker") -> Task:
    """Convert a MiniF2FProblem to a Task object."""
    rubric = MiniF2FRubric(
        benchmark="minif2f",
        max_score=1.0,
        partial_credit_for_syntax=0.2,
    )
    return Task(
        name=problem.problem_id,
        description=problem.problem_statement,
        assigned_to=worker,
        resources=[],  # MiniF2F problems don't have input files
        evaluator=rubric,
    )


def load_minif2f_to_database(
    data_dir: Path | None = None,
    limit: int | None = None,
    worker: "BaseWorker | None" = None,
) -> list[UUID]:
    """
    Load MiniF2F problems into database using the Task facade.

    This function creates Task objects and uses the Task persistence layer
    to create Experiment, Run placeholder, and Resource records.

    Args:
        data_dir: Base data directory (defaults to project data/ directory)
        limit: Optional limit on number of problems to load
        worker: The worker to assign to tasks (required for Task-based loading)

    Returns:
        List of created experiment IDs

    Raises:
        ValueError: If worker is not provided

    Example:
        >>> worker = ReActWorker(model="gpt-4o", config=MINIF2F_CONFIG)
        >>> experiment_ids = load_minif2f_to_database(worker=worker, limit=10)
    """
    if worker is None:
        raise ValueError("worker is required for Task-based loading")

    # Download/clone repository
    minif2f_dir = download_minif2f(data_dir)

    # Parse problems
    problems = parse_lean_problems(minif2f_dir, limit=limit)

    if not problems:
        print("   No problems found to load", file=sys.stderr)
        return []

    print(
        f"Saving {len(problems)} problems to database using Task facade...",
        file=sys.stderr,
        flush=True,
    )

    return load_benchmark_to_database(
        items=iter(problems),
        item_to_task=_minif2f_item_to_task,
        benchmark_name=BenchmarkName.MINIF2F.value,
        worker=worker,
        total=len(problems),
    )
