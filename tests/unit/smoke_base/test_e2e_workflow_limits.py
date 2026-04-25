from pathlib import Path


def test_e2e_smoke_matrix_is_serialized_for_e2b_quota() -> None:
    workflow = Path(".github/workflows/e2e-benchmarks.yml").read_text()

    strategy_start = workflow.index("    strategy:")
    runs_on_start = workflow.index("    runs-on:", strategy_start)
    strategy_block = workflow[strategy_start:runs_on_start]

    assert "      max-parallel: 1\n" in strategy_block
