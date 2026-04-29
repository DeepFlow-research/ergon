"""Application jobs should hydrate definition tasks through persistence helpers."""

from pathlib import Path


def test_inngest_jobs_do_not_query_definition_tables_directly() -> None:
    runtime_dir = Path("ergon_core/ergon_core/core/application/jobs")
    forbidden = (
        "ExperimentDefinitionTask",
        "ExperimentDefinitionInstance",
    )

    offenders = []
    for path in runtime_dir.glob("*.py"):
        text = path.read_text()
        if any(token in text for token in forbidden):
            offenders.append(str(path))

    assert offenders == []
