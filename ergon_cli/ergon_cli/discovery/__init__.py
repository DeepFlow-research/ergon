"""Temporary explicit builtin discovery for CLI listing commands.

PR 05 moves this catalogue behind builtins-owned metadata.
"""

from ergon_builtins.benchmarks.catalog import benchmark_cli_metadata

_WORKER_ROWS = (
    ("react-v1", "ReActWorker"),
    ("training-stub", "TrainingStubWorker"),
)
_EVALUATOR_ROWS = (
    ("gdpeval-staged-rubric", "StagedRubric"),
    ("minif2f-rubric", "MiniF2FRubric"),
    ("researchrubrics-rubric", "ResearchRubricsRubric"),
    ("swebench-rubric", "SWEBenchRubric"),
)


def list_benchmarks() -> list[list[str]]:
    return [
        [metadata.slug, metadata.name, metadata.description]
        for metadata in sorted(benchmark_cli_metadata().values(), key=lambda item: item.slug)
    ]


def list_workers() -> list[list[str]]:
    return [list(row) for row in sorted(_WORKER_ROWS)]


def list_evaluators() -> list[list[str]]:
    return [list(row) for row in sorted(_EVALUATOR_ROWS)]
