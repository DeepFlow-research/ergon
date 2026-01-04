"""MiniF2F data loading."""

import subprocess
import sys
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from h_arcane.core.db.connection import get_engine
from h_arcane.core.db.models import Experiment
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.minif2f.schemas import MiniF2FProblem
from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric

# Default paths relative to project root
DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

MINIF2F_REPO = "https://github.com/facebookresearch/miniF2F"


def download_minif2f(data_dir: Path | None = None) -> Path:
    """Clone MiniF2F repo if not exists.

    Args:
        data_dir: Base data directory (defaults to project data/ directory)

    Returns:
        Path to minif2f directory
    """
    if data_dir is None:
        data_dir = DATA_DIR

    minif2f_dir = data_dir / "raw" / "minif2f"
    if not minif2f_dir.exists():
        print(f"📥 Cloning MiniF2F repository to {minif2f_dir}...", file=sys.stderr)
        subprocess.run(
            ["git", "clone", MINIF2F_REPO, str(minif2f_dir)],
            check=True,
        )
        print("   ✅ Cloned MiniF2F repository", file=sys.stderr)
    else:
        print(f"   ✅ MiniF2F repository already exists at {minif2f_dir}", file=sys.stderr)

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
    import re

    problems = []

    for split in ["valid", "test"]:
        lean_file = minif2f_dir / "lean" / "src" / f"{split}.lean"
        if not lean_file.exists():
            print(f"   ⚠️  File not found: {lean_file}", file=sys.stderr)
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
                        f"   ⚠️  Failed to parse theorem {theorem_name}: {e}",
                        file=sys.stderr,
                    )
                    continue

            print(
                f"   📂 Found {len([m for m in re.finditer(theorem_pattern, content, re.DOTALL)])} theorems in {split}.lean",
                file=sys.stderr,
            )

        except Exception as e:
            print(f"   ⚠️  Failed to read {lean_file}: {e}", file=sys.stderr)
            continue

        if limit and len(problems) >= limit:
            break

    print(f"   ✅ Parsed {len(problems)} problems", file=sys.stderr)
    return problems


def load_minif2f_to_database(data_dir: Path | None = None, limit: int | None = None) -> list[UUID]:
    """Load MiniF2F problems into database as Experiments.

    Args:
        data_dir: Base data directory (defaults to project data/ directory)
        limit: Optional limit on number of problems to load

    Returns:
        List of experiment UUIDs
    """
    # Download/clone repository
    minif2f_dir = download_minif2f(data_dir)

    # Parse problems
    problems = parse_lean_problems(minif2f_dir, limit=limit)

    if not problems:
        print("   ⚠️  No problems found to load", file=sys.stderr)
        return []

    # Load to database
    experiment_ids = []
    total = len(problems)

    print(f"💾 Saving {total} problems to database...", file=sys.stderr, flush=True)

    engine = get_engine()
    session = Session(engine)

    try:
        for idx, problem in enumerate(problems, 1):
            print(
                f"   Processing problem {idx}/{total}: {problem.problem_id}...",
                file=sys.stderr,
                flush=True,
            )

            # Check if experiment already exists
            existing_experiment = session.exec(
                select(Experiment).where(
                    Experiment.benchmark_name == BenchmarkName.MINIF2F,
                    Experiment.task_id == problem.problem_id,
                )
            ).first()

            if existing_experiment:
                print(
                    f"      ⚠️  Experiment already exists (ID: {existing_experiment.id})",
                    file=sys.stderr,
                    flush=True,
                )
                experiment_ids.append(existing_experiment.id)
                continue

            rubric = MiniF2FRubric(
                benchmark="minif2f",
                max_score=1.0,
                partial_credit_for_syntax=0.2,
            )
            ground_truth_rubric = rubric.model_dump()

            experiment = Experiment(
                benchmark_name=BenchmarkName.MINIF2F,
                task_id=problem.problem_id,
                task_description=problem.problem_statement,
                ground_truth_rubric=ground_truth_rubric,
                benchmark_specific_data={
                    "split": problem.split,
                    "ground_truth_proof": problem.ground_truth_proof,
                },
                category=f"minif2f-{problem.split}",
            )

            session.add(experiment)
            session.commit()
            session.refresh(experiment)

            experiment_ids.append(experiment.id)
            print(
                f"      ✅ Created experiment (ID: {experiment.id})",
                file=sys.stderr,
                flush=True,
            )

    except Exception as e:
        session.rollback()
        print(f"   ❌ Error loading to database: {e}", file=sys.stderr)
        raise
    finally:
        session.close()

    print(f"   ✅ Loaded {len(experiment_ids)} experiments", file=sys.stderr)
    return experiment_ids
