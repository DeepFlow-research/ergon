import argparse

from ergon_cli.domains.experiments.commands import handle_experiment


def register_experiment_parser(subparsers: argparse._SubParsersAction) -> None:
    experiment = subparsers.add_parser("experiment", help="Experiment lifecycle")
    experiment.set_defaults(handler=handle_experiment)
    experiment_sub = experiment.add_subparsers(dest="experiment_action")
    experiment_show = experiment_sub.add_parser("show", help="Show experiment detail")
    experiment_show.add_argument("experiment_id", help="Experiment UUID")
    experiment_list = experiment_sub.add_parser("list", help="List experiments")
    experiment_list.add_argument("--limit", type=int, default=50, help="Number of experiments")
    experiment_samples = experiment_sub.add_parser("samples", help="List samples in an experiment")
    experiment_samples.add_argument("experiment_id", help="Experiment UUID")
    experiment_invocations = experiment_sub.add_parser(
        "sampler-invocations",
        help="List sampler invocations for an experiment",
    )
    experiment_invocations.add_argument("experiment_id", help="Experiment UUID")
