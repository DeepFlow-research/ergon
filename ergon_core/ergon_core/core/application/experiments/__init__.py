__all__ = ["run_experiment"]


def __getattr__(name: str) -> object:
    if name == "run_experiment":
        from ergon_core.core.application.experiments.service import run_experiment

        return run_experiment
    raise AttributeError(name)
