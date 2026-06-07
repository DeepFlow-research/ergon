"""Deprecated compatibility shim for the TRL example runner."""

from warnings import warn

from ergon_infra.training.config import TrainingConfig


def run_trl_training(config: TrainingConfig) -> int:
    warn(
        "ergon_infra.training.trl_runner.run_trl_training is deprecated; "
        "use examples.training.trl_single_agent_stochastic.run_trl_training",
        DeprecationWarning,
        stacklevel=2,
    )
    from examples.training.trl_single_agent_stochastic import run_trl_training as run_example

    return run_example(config)
