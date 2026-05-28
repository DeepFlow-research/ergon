import importlib
from pathlib import Path


def test_trl_single_agent_stochastic_imports_without_ergon_core() -> None:
    module = importlib.import_module("examples.training.trl_single_agent_stochastic")
    source = Path(module.__file__).read_text()

    assert "single-agent stochastic SMDP/POMDP baseline" in (module.__doc__ or "")
    assert hasattr(module, "run_trl_training")
    assert "ergon_core" not in source
