"""Unit tests for the magym CLI and setup helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from h_arcane.cli.main import build_parser, main
from h_arcane.core.runner import ExecutionResult
from h_arcane.core.task import TaskStatus
from h_arcane.services.setup.benchmark_preparation_service import BenchmarkPreparationService
from h_arcane.services.setup.benchmark_run_service import BenchmarkRunService
from h_arcane.services.setup.common import parse_env_file


def test_parse_env_file_reads_simple_key_values(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=test-openai-key",
                "HF_TOKEN='test-hf-token'",
                "# comment",
                "",
            ]
        ),
        encoding="utf-8",
    )

    values = parse_env_file(env_file)

    assert values["OPENAI_API_KEY"] == "test-openai-key"
    assert values["HF_TOKEN"] == "test-hf-token"


def test_build_parser_parses_benchmark_seed_command():
    parser = build_parser()

    args = parser.parse_args(
        [
            "benchmark",
            "seed",
            "researchrubrics",
            "--database",
            "test",
            "--limit",
            "3",
        ]
    )

    assert args.command == "benchmark"
    assert args.benchmark_command == "seed"
    assert args.benchmarks == ["researchrubrics"]
    assert args.database == "test"
    assert args.limit == 3


def test_benchmark_preparation_service_lists_supported_benchmarks():
    service = BenchmarkPreparationService()

    assert service.supported_benchmarks() == ("minif2f", "researchrubrics")


def test_build_parser_parses_benchmark_run_command():
    parser = build_parser()

    args = parser.parse_args(
        [
            "benchmark",
            "run",
            "smoke_test",
            "--workflow",
            "single",
            "--cohort-name",
            "demo-cohort",
            "--timeout",
            "60",
        ]
    )

    assert args.command == "benchmark"
    assert args.benchmark_command == "run"
    assert args.benchmark == "smoke_test"
    assert args.workflow == "single"
    assert args.cohort_name == "demo-cohort"
    assert args.timeout == 60


def test_build_parser_parses_seeded_benchmark_run_command():
    parser = build_parser()

    args = parser.parse_args(
        [
            "benchmark",
            "run",
            "minif2f",
            "--task-id",
            "amc12a_2008_p25",
            "--cohort-name",
            "minif2f-demo",
            "--limit",
            "2",
        ]
    )

    assert args.command == "benchmark"
    assert args.benchmark_command == "run"
    assert args.benchmark == "minif2f"
    assert args.task_id == ["amc12a_2008_p25"]
    assert args.cohort_name == "minif2f-demo"
    assert args.limit == 2


def test_main_lists_supported_benchmarks(capsys):
    exit_code = main(["benchmark", "list"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "minif2f" in captured.out
    assert "researchrubrics" in captured.out


def test_main_runs_benchmark_workflow_and_prints_summary(capsys, monkeypatch):
    async def fake_run(self, **kwargs):
        assert kwargs["benchmark"] == "smoke_test"
        assert kwargs["workflow_names"] == ["single"]
        assert kwargs["cohort_name"] == "demo-cohort"
        return {
            "single": ExecutionResult(
                success=True,
                status=TaskStatus.COMPLETED,
                duration_seconds=1.2,
            )
        }

    monkeypatch.setattr(BenchmarkRunService, "run", fake_run)

    exit_code = main(
        [
            "benchmark",
            "run",
            "smoke_test",
            "--workflow",
            "single",
            "--cohort-name",
            "demo-cohort",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "smoke_test/single: PASS" in captured.out


def test_main_runs_seeded_benchmark_and_prints_summary(capsys, monkeypatch):
    async def fake_run(self, **kwargs):
        assert kwargs["benchmark"] == "minif2f"
        assert kwargs["task_ids"] == ["amc12a_2008_p25"]
        assert kwargs["cohort_name"] == "demo-cohort"
        return {
            "amc12a_2008_p25": ExecutionResult(
                success=True,
                status=TaskStatus.COMPLETED,
                duration_seconds=2.0,
            )
        }

    monkeypatch.setattr(BenchmarkRunService, "run", fake_run)

    exit_code = main(
        [
            "benchmark",
            "run",
            "minif2f",
            "--task-id",
            "amc12a_2008_p25",
            "--cohort-name",
            "demo-cohort",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "minif2f/amc12a_2008_p25: PASS" in captured.out


def test_main_rejects_missing_selector_for_seeded_benchmark():
    with pytest.raises(ValueError, match="exactly one selector"):
        main(
            [
                "benchmark",
                "run",
                "minif2f",
                "--cohort-name",
                "demo-cohort",
            ]
        )


def test_main_rejects_workflow_selector_for_seeded_benchmark():
    with pytest.raises(ValueError, match="do not support --workflow"):
        main(
            [
                "benchmark",
                "run",
                "researchrubrics",
                "--workflow",
                "single",
                "--cohort-name",
                "demo-cohort",
            ]
        )
