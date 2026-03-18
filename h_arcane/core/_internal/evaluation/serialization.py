"""
Rubric serialization/deserialization utilities.

This module handles converting between stored evaluator configs (JSON)
and live rubric objects that can be used for evaluation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from h_arcane.benchmarks.types import AnyRubric


from h_arcane.benchmarks.gdpeval.rubric import StagedRubric
from h_arcane.benchmarks.minif2f.rubric import MiniF2FRubric
from h_arcane.benchmarks.researchrubrics.rubric import ResearchRubricsRubric
from h_arcane.benchmarks.smoke_test.rubric import SmokeTestRubric


def deserialize_rubric(evaluator_type: str, config: dict) -> "AnyRubric":
    """
    Reconstruct a rubric object from its stored type and config.

    Args:
        evaluator_type: The class name of the rubric (e.g., "StagedRubric")
        config: The serialized rubric configuration

    Returns:
        A rubric instance that can be used for evaluation

    Raises:
        ValueError: If the evaluator_type is unknown
    """
    # Map evaluator type names to their classes
    if evaluator_type == "StagedRubric":
        return StagedRubric.model_validate(config)
    elif evaluator_type == "MiniF2FRubric":
        return MiniF2FRubric.model_validate(config)
    elif evaluator_type == "ResearchRubricsRubric":
        return ResearchRubricsRubric.model_validate(config)
    elif evaluator_type == "SmokeTestRubric":
        return SmokeTestRubric.model_validate(config)
    else:
        raise ValueError(
            f"Unknown evaluator type: {evaluator_type}. "
            f"Known types: ['StagedRubric', 'MiniF2FRubric', 'ResearchRubricsRubric', 'SmokeTestRubric']"
        )


def serialize_rubric(rubric: "AnyRubric") -> tuple[str, dict]:
    """
    Serialize a rubric for storage.

    Args:
        rubric: The rubric to serialize

    Returns:
        Tuple of (type_name, config_dict)
    """
    return (
        type(rubric).__name__,
        rubric.model_dump(mode="json"),
    )
