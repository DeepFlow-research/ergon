import argparse

from ergon_cli.domains.experiments.commands import handle_experiment


def register_experiment_parser(subparsers: argparse._SubParsersAction) -> None:
    experiment = subparsers.add_parser("experiment", help="Experiment lifecycle")
    experiment.set_defaults(handler=handle_experiment)
    experiment_sub = experiment.add_subparsers(dest="experiment_action")
    experiment_show = experiment_sub.add_parser("show", help="Show experiment detail")
    experiment_show.add_argument("definition_id", help="Experiment UUID")
    experiment_list = experiment_sub.add_parser("list", help="List experiments")
    experiment_list.add_argument("--limit", type=int, default=50, help="Number of experiments")
    experiment_sub.add_parser("tags", help="List distinct experiment tags")
    experiment_by_tag = experiment_sub.add_parser(
        "by-tag", help="List definitions for an experiment tag"
    )
    experiment_by_tag.add_argument("tag", help="Experiment tag")
