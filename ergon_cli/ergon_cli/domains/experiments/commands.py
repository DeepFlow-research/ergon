from argparse import Namespace

from ergon_cli.domains.experiments.models import (
    ListByTagCommand,
    ListExperimentsCommand,
    ListTagsCommand,
    ShowExperimentCommand,
)
from ergon_cli.domains.experiments.service import (
    list_by_tag,
    list_experiments,
    list_tags,
    show_experiment,
)
from ergon_cli.shared import exit_codes
from ergon_cli.shared.errors import CliError
from ergon_cli.shared.output import render_text
from ergon_cli.shared.parsing import parse_uuid


async def handle_experiment(args: Namespace) -> int:
    if args.experiment_action == "show":
        return handle_experiment_show(args)
    if args.experiment_action == "list":
        return handle_experiment_list(args)
    if args.experiment_action == "tags":
        return handle_experiment_tags(args)
    if args.experiment_action == "by-tag":
        return handle_experiment_by_tag(args)
    print("Usage: ergon experiment {show|list|tags|by-tag}")
    return exit_codes.RUNTIME_ERROR


def handle_experiment_show(args: Namespace) -> int:
    try:
        detail = show_experiment(
            ShowExperimentCommand(
                definition_id=parse_uuid(args.definition_id, field_name="definition_id")
            )
        )
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    experiment = detail.experiment
    lines = [
        f"DEFINITION_ID={experiment.definition_id}",
        f"NAME={experiment.name}",
        f"BENCHMARK={experiment.benchmark_type}",
        f"STATUS={experiment.status}",
        f"SAMPLE_COUNT={experiment.sample_count}",
        f"RUN_COUNT={experiment.run_count}",
    ]
    if experiment.default_model_target is not None:
        lines.append(f"DEFAULT_MODEL={experiment.default_model_target}")
    if experiment.default_evaluator_slug is not None:
        lines.append(f"DEFAULT_EVALUATOR={experiment.default_evaluator_slug}")
    if detail.sample_selection:
        lines.append(f"SAMPLE_SELECTION={detail.sample_selection}")
    if detail.runs:
        lines.append("SAMPLES")
        lines.extend(
            "\t".join(
                [
                    str(run.sample_id),
                    run.instance_key,
                    run.status,
                    "" if run.model_target is None else run.model_target,
                ]
            )
            for run in detail.runs
        )
    print(render_text(lines))
    return exit_codes.OK


def handle_experiment_list(args: Namespace) -> int:
    experiments = list_experiments(ListExperimentsCommand(limit=args.limit))
    if not experiments:
        print("No experiments found.")
        return exit_codes.OK
    lines = ["DEFINITION_ID\tNAME\tBENCHMARK\tSTATUS\tSAMPLES\tATTEMPTS\tMODEL"]
    lines.extend(
        "\t".join(
            [
                str(experiment.definition_id),
                experiment.name,
                experiment.benchmark_type,
                experiment.status,
                str(experiment.sample_count),
                str(experiment.run_count),
                "" if experiment.default_model_target is None else experiment.default_model_target,
            ]
        )
        for experiment in experiments
    )
    print(render_text(lines))
    return exit_codes.OK


def handle_experiment_tags(args: Namespace) -> int:
    del args
    tags = list_tags(ListTagsCommand())
    if not tags:
        print("No experiment tags found.")
        return exit_codes.OK
    print(render_text(tags))
    return exit_codes.OK


def handle_experiment_by_tag(args: Namespace) -> int:
    rows = list_by_tag(ListByTagCommand(tag=args.tag))
    if not rows:
        print(f"No definitions found for experiment tag {args.tag!r}.")
        return exit_codes.OK
    lines = ["DEFINITION_ID\tNAME\tBENCHMARK\tLATEST_RUN_STATUS"]
    lines.extend(
        "\t".join(
            [
                str(row.definition_id),
                row.name,
                row.benchmark_type,
                "" if row.latest_run_status is None else row.latest_run_status,
            ]
        )
        for row in rows
    )
    print(render_text(lines))
    return exit_codes.OK
