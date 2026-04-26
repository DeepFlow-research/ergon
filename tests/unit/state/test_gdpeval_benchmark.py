"""Tests for GDPEval benchmark task materialization."""

from pathlib import Path

from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPTaskConfig


def test_load_task_configs_returns_typed_payloads(monkeypatch):
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.benchmark.load_task_ids",
        lambda split, repo_id, limit: ["task_001"],
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.benchmark.find_reference_files",
        lambda task_id, repo_id: [Path("/tmp/reference.pdf")],
    )

    benchmark = GDPEvalBenchmark(dataset_repo="fake/repo", split="train", limit=1)

    assert benchmark._load_task_configs() == [
        GDPTaskConfig(
            task_id="task_001",
            workflow_type="document_processing",
            reference_files=["/tmp/reference.pdf"],
        )
    ]


def test_build_instances_uses_typed_payloads(monkeypatch):
    monkeypatch.setattr(
        GDPEvalBenchmark,
        "_load_task_configs",
        lambda self: [
            GDPTaskConfig(
                task_id="task_001",
                workflow_type="document_processing",
                reference_files=["/tmp/reference.pdf"],
            )
        ],
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.benchmark.extract_task_description",
        lambda task_id, repo_id: "Process the reference document.",
    )

    task = GDPEvalBenchmark(dataset_repo="fake/repo").build_instances()["default"][0]

    assert task.task_payload == GDPTaskConfig(
        task_id="task_001",
        workflow_type="document_processing",
        reference_files=["/tmp/reference.pdf"],
    )
