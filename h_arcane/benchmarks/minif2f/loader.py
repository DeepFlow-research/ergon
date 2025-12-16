"""MiniF2F data loading."""

import subprocess
import sys
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from h_arcane.db.connection import get_engine
from h_arcane.db.models import Experiment
from h_arcane.schemas.base import BenchmarkName
from h_arcane.benchmarks.minif2f.schemas import MiniF2FProblem

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


def extract_problem_from_lean(content: str, problem_id: str, split: str) -> MiniF2FProblem:
    """Extract problem statement and ground truth proof from Lean file.

    Args:
        content: Full content of the Lean file
        problem_id: Problem identifier (filename without .lean)
        split: Dataset split ("valid" or "test")

    Returns:
        MiniF2FProblem with parsed statement and proof
    """
    # MiniF2F files typically have:
    # - Import statements at top
    # - Theorem statement
    # - Proof (by ...)
    lines = content.split("\n")

    # Find theorem statement (usually starts with "theorem" or "example")
    theorem_start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(("theorem ", "example ")):
            theorem_start = i
            break

    if theorem_start is None:
        # Fallback: use entire content
        problem_statement = content
        ground_truth_proof = content
    else:
        # Extract theorem statement (up to :=)
        theorem_lines = []
        for i in range(theorem_start, len(lines)):
            line = lines[i]
            theorem_lines.append(line)
            if ":=" in line:
                break

        problem_statement = "\n".join(theorem_lines)
        ground_truth_proof = content

    return MiniF2FProblem(
        problem_id=problem_id,
        problem_statement=problem_statement.strip(),
        ground_truth_proof=ground_truth_proof.strip(),
        split=split,
        lean_file_path=None,
    )


def parse_lean_problems(minif2f_dir: Path, limit: int | None = None) -> list[MiniF2FProblem]:
    """Parse Lean files from lean/valid/ and lean/test/ directories.

    Args:
        minif2f_dir: Path to MiniF2F repository root
        limit: Optional limit on number of problems to load

    Returns:
        List of MiniF2FProblem objects
    """
    problems = []

    for split in ["valid", "test"]:
        lean_dir = minif2f_dir / "lean" / split
        if not lean_dir.exists():
            print(f"   ⚠️  Directory not found: {lean_dir}", file=sys.stderr)
            continue

        lean_files = list(lean_dir.glob("*.lean"))
        print(f"   📂 Found {len(lean_files)} Lean files in {split}/", file=sys.stderr)

        for lean_file in lean_files:
            if limit and len(problems) >= limit:
                break

            try:
                content = lean_file.read_text(encoding="utf-8")
                problem = extract_problem_from_lean(content, lean_file.stem, split)
                problem.lean_file_path = lean_file
                problems.append(problem)
            except Exception as e:
                print(
                    f"   ⚠️  Failed to parse {lean_file.name}: {e}",
                    file=sys.stderr,
                )
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

            # Create experiment with ground truth proof as rubric
            # For MiniF2F, we use a simple ProofVerificationRule
            ground_truth_rubric = {
                "stages": [
                    {
                        "name": "proof_verification",
                        "max_points": 1.0,
                        "min_score_to_pass": 1.0,
                        "is_required": True,
                        "on_failure_action": "skip_remaining",
                        "on_failure_score": 0.0,
                        "rules": [
                            {
                                "type": "proof_verification",
                                "name": "proof_correctness",
                                "description": "Verify that the proof is correct",
                                "weight": 1.0,
                                "problem_statement": problem.problem_statement,
                                "ground_truth_proof": problem.ground_truth_proof,
                                "formal_system": "lean",
                            }
                        ],
                    }
                ],
                "max_total_score": 1.0,
                "category_name": f"MiniF2F-{problem.split}",
            }

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
