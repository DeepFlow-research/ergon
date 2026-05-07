from pathlib import Path

from pydantic import ValidationError

from ergon_ingestion.models import (
    ImportSource,
    ParsedAnnotation,
    ParsedReducer,
    ParsedResource,
    ParsedRun,
)
from ergon_ingestion.registry import get_importer, list_importers


def test_parsed_run_requires_stable_source_identity() -> None:
    with pytest_raises_validation_error("source_run_id"):
        ParsedRun.model_validate(
            {
                "instance_key": "gap-row-1",
                "description": "Imported GAP row 1",
                "schema_fit_class": "row-record",
            }
        )


def test_parsed_run_accepts_annotations_resources_and_reducers() -> None:
    run = ParsedRun(
        source_run_id="gap-row-1",
        instance_key="gap-row-1",
        description="Imported GAP row 1",
        schema_fit_class="row-record",
        observed_fields={"t_safe": True, "tc_safe": False},
        missing_fields=["full_runtime_environment"],
        annotations=[
            ParsedAnnotation(namespace="gap.labels", payload={"t_safe": True, "tc_safe": False})
        ],
        resources=[
            ParsedResource(
                name="source-row.json",
                kind="import",
                mime_type="application/json",
                payload={"row": 1},
            )
        ],
        reducers=[
            ParsedReducer(
                name="gap.text_safety",
                kind="original",
                output={"safe": True},
                fields_read=["t_safe"],
            )
        ],
    )

    assert run.source_run_id == "gap-row-1"
    assert run.resources[0].payload == {"row": 1}
    assert run.reducers[0].fields_read == ["t_safe"]


def test_import_source_expands_input_path() -> None:
    source = ImportSource(dataset="gap", input_path="data/gap.parquet", batch_id="paper-rq1-v1")

    assert source.input_path == Path("data/gap.parquet")


def test_registry_exposes_all_planned_dataset_importers() -> None:
    slugs = {entry.slug for entry in list_importers()}

    assert {
        "gap",
        "maestro",
        "copra",
        "tot_crosswords",
        "tot_game24",
        "tau_bench",
        "agentharm",
        "openhands_swe_rebench",
        "swe_smith",
        "weblinx",
        "agent_reward_bench",
        "stabletoolbench",
        "atbench",
        "bfcl",
        "debate_mallm",
        "miniwob",
        "math",
        "gsm8k",
        "humaneval",
        "gpqa",
        "mmlu",
        "swebench_cross_harness",
        "mle_bench",
        "swe_lancer",
        "browsecomp",
    }.issubset(slugs)


def test_get_importer_rejects_unknown_slug() -> None:
    with pytest_raises_key_error("unknown dataset importer"):
        get_importer("missing")


class pytest_raises_validation_error:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        assert exc_type is ValidationError
        assert self.expected in str(exc)
        return True


class pytest_raises_key_error:
    def __init__(self, expected: str) -> None:
        self.expected = expected

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, traceback) -> bool:
        assert exc_type is KeyError
        assert self.expected in str(exc)
        return True
