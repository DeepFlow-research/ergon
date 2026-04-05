"""Experiment command (placeholder for direct experiment composition)."""

from argparse import Namespace


def handle_experiment(args: Namespace) -> int:
    print("Direct experiment composition from CLI is not yet supported.")
    print("Use Python API: Experiment.from_single_worker(...)")
    return 0
