"""Unit tests for the magym CLI and setup helpers."""

from __future__ import annotations

from pathlib import Path

from h_arcane.cli.main import build_parser, main
from h_arcane.services.setup.benchmark_preparation_service import BenchmarkPreparationService
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


def test_main_lists_supported_benchmarks(capsys):
    exit_code = main(["benchmark", "list"])

    captured = capsys.readouterr()

    assert exit_code == 0
    assert "minif2f" in captured.out
    assert "researchrubrics" in captured.out
