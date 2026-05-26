from argparse import Namespace

from ergon_cli.domains.experiments.models import (
    ExperimentSamplesCommand,
    ExperimentSamplerInvocationsCommand,
    ListByTagCommand,
    ListExperimentsCommand,
    ListTagsCommand,
    ShowExperimentCommand,
)
from ergon_cli.domains.experiments.service import (
    list_by_tag,
    list_experiment_samples,
    list_experiment_sampler_invocations,
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
    if args.experiment_action == "samples":
        return handle_experiment_samples(args)
    if args.experiment_action == "sampler-invocations":
        return handle_experiment_sampler_invocations(args)
    if args.experiment_action == "tags":
        return handle_experiment_tags(args)
    if args.experiment_action == "by-tag":
        return handle_experiment_by_tag(args)
    print("Usage: ergon experiment {show|list|samples|sampler-invocations|tags|by-tag}")
    return exit_codes.RUNTIME_ERROR


def handle_experiment_show(args: Namespace) -> int:
    try:
        detail = show_experiment(
            ShowExperimentCommand(
                experiment_id=parse_uuid(args.experiment_id, field_name="experiment_id")
            )
        )
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    lines = [
        f"EXPERIMENT_ID={detail.experiment_id}",
        f"NAME={detail.name}",
        f"SAMPLE_COUNT={detail.sample_count}",
        f"SAMPLER_INVOCATIONS={detail.sampler_invocation_count}",
    ]
    if detail.environments:
        lines.append("ENVIRONMENTS")
        lines.extend(
            "\t".join(
                [
                    environment.environment_name,
                    environment.source_mode,
                    str(environment.sample_count),
                    str(environment.selected_count),
                ]
            )
            for environment in detail.environments
        )
    if detail.samples:
        lines.append("SAMPLES")
        lines.extend(
            "\t".join(
                [
                    str(sample.sample_id),
                    sample.environment_name,
                    sample.sample_key,
                    sample.status,
                ]
            )
            for sample in detail.samples
        )
    print(render_text(lines))
    return exit_codes.OK


def handle_experiment_samples(args: Namespace) -> int:
    try:
        result = list_experiment_samples(
            ExperimentSamplesCommand(
                experiment_id=parse_uuid(args.experiment_id, field_name="experiment_id")
            )
        )
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    if not result.samples:
        print("No samples found.")
        return exit_codes.OK
    lines = ["SAMPLE_ID\tENVIRONMENT\tKEY\tSTATUS"]
    lines.extend(
        "\t".join(
            [str(sample.sample_id), sample.environment_name, sample.sample_key, sample.status]
        )
        for sample in result.samples
    )
    print(render_text(lines))
    return exit_codes.OK


def handle_experiment_sampler_invocations(args: Namespace) -> int:
    try:
        result = list_experiment_sampler_invocations(
            ExperimentSamplerInvocationsCommand(
                experiment_id=parse_uuid(args.experiment_id, field_name="experiment_id")
            )
        )
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    if not result.invocations:
        print("No sampler invocations found.")
        return exit_codes.OK
    lines = ["SAMPLER_INVOCATION_ID\tSAMPLER\tK\tCANDIDATES\tSELECTED"]
    lines.extend(
        "\t".join(
            [
                str(invocation.sampler_invocation_id),
                invocation.sampler_name,
                str(invocation.requested_k),
                str(invocation.candidate_pool_size),
                str(invocation.selected_count),
            ]
        )
        for invocation in result.invocations
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
