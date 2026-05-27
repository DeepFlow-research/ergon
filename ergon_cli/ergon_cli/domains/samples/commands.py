from argparse import Namespace

from ergon_cli.domains.samples.models import (
    ListSamplesCommand,
    SampleEventsCommand,
    SampleGraphCommand,
    SampleStatusCommand,
)
from ergon_cli.domains.samples.service import (
    get_sample_detail,
    get_sample_graph,
    get_sample_status,
    list_sample_events,
    list_samples,
)
from ergon_cli.shared import exit_codes
from ergon_cli.shared.errors import CliError
from ergon_cli.shared.output import render_table, render_text
from ergon_cli.shared.parsing import parse_uuid


def handle_sample(args: Namespace) -> int:
    if args.sample_action == "list":
        return list_samples_command(args)
    if args.sample_action == "status":
        return status_sample_command(args)
    if args.sample_action == "show":
        return show_sample_command(args)
    if args.sample_action == "events":
        return sample_events_command(args)
    if args.sample_action == "graph":
        return sample_graph_command(args)
    print("Usage: ergon sample {list|status|show|events|graph}")
    return exit_codes.RUNTIME_ERROR


def list_samples_command(args: Namespace) -> int:
    try:
        result = list_samples(
            ListSamplesCommand(
                limit=args.limit,
                status=args.status,
                experiment=args.experiment,
            )
        )
    except CliError as exc:
        print(exc.message)
        return exc.exit_code

    if not result.samples:
        parts = ["No samples found"]
        if result.status:
            parts.append(f"with status={result.status!r}")
        if result.experiment:
            parts.append(f"for experiment={result.experiment!r}")
        print(" ".join(parts))
        return exit_codes.OK

    print(
        render_table(
            ["ID (short)", "Status", "Created", "Duration", "Full ID"],
            [
                [str(sample.id)[:8], sample.status, sample.created, sample.duration, str(sample.id)]
                for sample in result.samples
            ],
        )
    )
    return exit_codes.OK


def status_sample_command(args: Namespace) -> int:
    try:
        sample = get_sample_status(SampleStatusCommand(sample_id=parse_uuid(args.sample_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    lines = [
        f"sample_id:              {sample.id}",
        f"status:                 {sample.status}",
        f"benchmark_type:         {sample.benchmark_type}",
        f"instance_key:           {sample.instance_key}",
    ]
    if sample.evaluator_slug is not None:
        lines.append(f"evaluator:              {sample.evaluator_slug}")
    if sample.model_target is not None:
        lines.append(f"model:                  {sample.model_target}")
    lines.append(f"created_at:             {sample.created}")
    if sample.started:
        lines.append(f"started_at:             {sample.started}")
    if sample.completed:
        lines.append(f"completed_at:           {sample.completed}")
    if sample.error_message:
        lines.append(f"error:                  {sample.error_message}")
    print(render_text(lines))
    return exit_codes.OK


def show_sample_command(args: Namespace) -> int:
    try:
        sample = get_sample_detail(SampleStatusCommand(sample_id=parse_uuid(args.sample_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    print(
        render_text(
            [
                f"sample_id:              {sample.sample_id}",
                f"experiment_id:          {sample.experiment_id}",
                f"environment_id:         {sample.environment_id}",
                f"environment:            {sample.environment_name}",
                f"sample_key:             {sample.sample_key}",
                f"status:                 {sample.status}",
            ]
        )
    )
    return exit_codes.OK


def sample_events_command(args: Namespace) -> int:
    try:
        events = list_sample_events(SampleEventsCommand(sample_id=parse_uuid(args.sample_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    if not events:
        print("No events found.")
        return exit_codes.OK
    lines = ["EVENT\tTARGET\tTIMESTAMP"]
    lines.extend("\t".join([event.event_type, event.target, event.timestamp]) for event in events)
    print(render_text(lines))
    return exit_codes.OK


def sample_graph_command(args: Namespace) -> int:
    try:
        graph = get_sample_graph(SampleGraphCommand(sample_id=parse_uuid(args.sample_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    lines = [
        f"nodes:                  {graph.node_count}",
        f"edges:                  {graph.edge_count}",
    ]
    if graph.nodes:
        lines.append("NODES")
        lines.extend(graph.nodes)
    print(render_text(lines))
    return exit_codes.OK
