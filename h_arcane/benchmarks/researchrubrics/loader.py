"""ResearchRubrics data loading from HuggingFace."""

import sys
from uuid import UUID

from datasets import Dataset, load_dataset
from huggingface_hub import HfApi
from sqlmodel import Session, select

from h_arcane.core._internal.db.connection import get_engine
from h_arcane.core._internal.db.models import Experiment
from h_arcane.benchmarks.enums import BenchmarkName
from h_arcane.benchmarks.researchrubrics.schemas import RubricCriterion
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric


def get_ablated_dataset_name() -> str:
    """Get ablated dataset name from HuggingFace credentials.

    Returns:
        Dataset name in format "{username}/researchrubrics-ablated"

    Raises:
        RuntimeError: If not logged in to HuggingFace
    """
    api = HfApi()
    try:
        user_info = api.whoami()
        username = user_info["name"]
        return f"{username}/researchrubrics-ablated"
    except Exception as e:
        raise RuntimeError(
            "Could not determine HuggingFace username. "
            "Please run 'huggingface-cli login' or provide ablated_dataset_name explicitly."
        ) from e


def load_researchrubrics_to_database(
    ablated_dataset_name: str | None = None,
    limit: int | None = None,
) -> list[UUID]:
    """Load ResearchRubrics from ablated HuggingFace dataset into database.

    The ablated dataset is a superset containing:
    - All original fields (sample_id, domain, prompt, rubrics, etc.)
    - Ablated prompts (ablated_prompt, ablation_type, removed_elements)

    Args:
        ablated_dataset_name: HuggingFace dataset name for ablated dataset
                             (e.g., "{username}/researchrubrics-ablated").
                             If None, auto-detects from HuggingFace credentials.
        limit: Optional limit on number of tasks to load

    Returns:
        List of experiment UUIDs
    """
    # Auto-detect dataset name if not provided
    if ablated_dataset_name is None:
        ablated_dataset_name = get_ablated_dataset_name()
        print(f"📦 Using ablated dataset: {ablated_dataset_name}", file=sys.stderr)

    # Load dataset from HuggingFace
    print(f"📥 Loading dataset from HuggingFace: {ablated_dataset_name}...", file=sys.stderr)
    ds_dict = load_dataset(ablated_dataset_name)
    ds: Dataset = ds_dict["train"]  # type: ignore[assignment]

    if limit:
        ds = ds.select(range(min(limit, len(ds))))
        print(f"   Limited to {len(ds)} samples", file=sys.stderr)

    # Load to database
    experiment_ids = []
    total = len(ds)

    print(f"💾 Saving {total} tasks to database...", file=sys.stderr, flush=True)

    engine = get_engine()
    session = Session(engine)

    try:
        for idx in range(total):
            row: dict = ds[idx]  # type: ignore[index]
            sample_id: str = row["sample_id"]
            print(
                f"   Processing task {idx + 1}/{total}: {sample_id}...",
                file=sys.stderr,
                flush=True,
            )

            # Check if experiment already exists
            existing_experiment = session.exec(
                select(Experiment).where(
                    Experiment.benchmark_name == BenchmarkName.RESEARCHRUBRICS,
                    Experiment.task_id == sample_id,
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

            # Parse rubrics into RubricCriterion objects
            rubric_criteria = [
                RubricCriterion(
                    criterion=r["criterion"],
                    axis=r["axis"],
                    weight=r["weight"],
                )
                for r in row["rubrics"]
            ]

            # Create rubric
            rubric = ResearchRubricsRubric(
                benchmark="researchrubrics",
                criteria=rubric_criteria,
            )
            ground_truth_rubric = rubric.model_dump()

            # Create experiment
            experiment = Experiment(
                benchmark_name=BenchmarkName.RESEARCHRUBRICS,
                task_id=sample_id,
                task_description=row["ablated_prompt"],
                ground_truth_rubric=ground_truth_rubric,
                benchmark_specific_data={
                    "domain": row["domain"],
                    "ablation_type": row.get("ablation_type"),
                    "removed_elements": row.get("removed_elements"),
                },
                category=row["domain"],
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
