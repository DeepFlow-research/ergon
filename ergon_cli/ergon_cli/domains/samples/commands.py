from argparse import Namespace

from ergon_cli.domains.samples.models import (
    CancelSampleCommand,
    ListSamplesCommand,
    SampleStatusCommand,
)
from ergon_cli.domains.samples.service import (
    cancel_existing_sample,
    get_sample_status,
    list_samples,
)
from ergon_cli.shared import exit_codes
from ergon_cli.shared.errors import CliError
from ergon_cli.shared.output import render_table, render_text
from ergon_cli.shared.parsing import parse_uuid


def handle_sample(args: Namespace) -> int:
    if args.sample_action == "list":
        return list_samples_command(args)
    if args.sample_action == "cancel":
        return cancel_sample_command(args)
    if args.sample_action == "status":
        return status_sample_command(args)
    print("Usage: ergon sample {list|status|cancel}")
    return exit_codes.RUNTIME_ERROR


def list_samples_command(args: Namespace) -> int:
    try:
        definition_id = (
            parse_uuid(args.definition_id, field_name="definition_id")
            if args.definition_id
            else None
        )
        result = list_samples(
            ListSamplesCommand(
                limit=args.limit,
                status=args.status,
                definition_id=definition_id,
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
        if result.definition_id:
            parts.append(f"for definition_id={str(result.definition_id)!r}")
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


def cancel_sample_command(args: Namespace) -> int:
    try:
        result = cancel_existing_sample(CancelSampleCommand(sample_id=parse_uuid(args.sample_id)))
    except CliError as exc:
        print(exc.message)
        return exc.exit_code
    print(
        render_text(
            [
                f"Sample {result.sample.id} cancelled.",
                f"  Status:  {result.sample.status}",
                "  Inngest: sample/cancelled event sent (in-flight functions will be killed)",
                "  Cleanup: sample/cleanup event sent (sandbox teardown scheduled)",
            ]
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
        f"definition_id:          {sample.definition_id}",
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
