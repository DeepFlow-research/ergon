"""Explicit builtin discovery for CLI listing commands."""

_BENCHMARK_ROWS = (
    ("gdpeval", "gdpeval", "Benchmark for GDP document-processing evaluation tasks."),
    ("minif2f", "minif2f", "Benchmark backed by MiniF2F theorem-proving tasks."),
    ("researchrubrics", "researchrubrics", "Benchmark backed by ScaleAI ResearchRubrics samples."),
    (
        "researchrubrics-vanilla",
        "researchrubrics-vanilla",
        "Vanilla ResearchRubrics baseline benchmark.",
    ),
    ("swebench-verified", "swebench-verified", "Benchmark backed by SWE-Bench Verified."),
)
_WORKER_ROWS = (
    ("react-worker", "ReActWorker"),
    ("training-stub-worker", "TrainingStubWorker"),
)
_EVALUATOR_ROWS = (
    ("gdpeval-staged-rubric", "StagedRubric"),
    ("minif2f-rubric", "MiniF2FRubric"),
    ("researchrubrics-rubric", "ResearchRubricsRubric"),
    ("swebench-rubric", "SWEBenchRubric"),
)


def list_benchmarks() -> list[list[str]]:
    return [list(row) for row in sorted(_BENCHMARK_ROWS)]


def list_workers() -> list[list[str]]:
    return [list(row) for row in sorted(_WORKER_ROWS)]


def list_evaluators() -> list[list[str]]:
    return [list(row) for row in sorted(_EVALUATOR_ROWS)]
