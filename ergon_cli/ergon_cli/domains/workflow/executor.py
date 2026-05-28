import argparse
import contextlib
import io
import json
import shlex
import time
from collections.abc import Callable
from typing import cast
from uuid import UUID

from ergon_cli.domains.workflow.models import WorkflowCommandContext, WorkflowCommandOutput
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from ergon_core.core.shared.json_types import JsonObject
from pydantic import BaseModel
from sqlmodel import Session

_RESOURCE_SCOPES = ("visible", "own", "input", "upstream", "children", "descendants")
_RESOURCE_KINDS = ("artifact", "import", "note", "output", "report", "search_cache")
_OUTPUT_FORMATS = ("text", "json")
_DEPENDENCY_DIRECTIONS = ("upstream", "downstream", "both")

_FORBIDDEN_CONTEXT_FLAGS = {
    "--sample-id",
    "--task-id",
    "--node-id",
    "--execution-id",
    "--sandbox-id",
    "--sandbox-task-key",
    "--environment-type",
}


def build_workflow_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow")
    sub = parser.add_subparsers(dest="group", required=True)

    inspect = sub.add_parser("inspect")
    inspect_sub = inspect.add_subparsers(dest="action", required=True)
    resource_list = inspect_sub.add_parser("resource-list")
    resource_list.add_argument("--scope", required=True, choices=_RESOURCE_SCOPES)
    resource_list.add_argument("--kind", choices=_RESOURCE_KINDS, default=None)
    resource_list.add_argument("--limit", type=int, default=50)
    resource_list.add_argument("--max-depth", type=int, default=3)
    resource_list.add_argument("--format", choices=_OUTPUT_FORMATS, default="text")

    resource_content = inspect_sub.add_parser("resource-content")
    resource_content.add_argument("--resource-id", required=True)
    resource_content.add_argument("--max-bytes", type=int, default=100_000)
    resource_content.add_argument("--format", choices=_OUTPUT_FORMATS, default="text")

    task_tree = inspect_sub.add_parser("task-tree")
    task_tree.add_argument("--format", choices=_OUTPUT_FORMATS, default="text")
    task_tree.add_argument("--parent-task-id", default=None)
    task_tree.add_argument("--wait-seconds", type=float, default=0)

    dependencies = inspect_sub.add_parser("task-dependencies")
    dependencies.add_argument("--direction", choices=_DEPENDENCY_DIRECTIONS, default="both")
    dependencies.add_argument("--format", choices=_OUTPUT_FORMATS, default="text")

    next_action = inspect_sub.add_parser("next-actions")
    next_action.add_argument("--manager-capable", action="store_true")
    next_action.add_argument("--format", choices=_OUTPUT_FORMATS, default="text")

    return parser


def execute_workflow_command(
    command: str,
    *,
    context: WorkflowCommandContext,
    session_factory: Callable[[], Session],
    service: WorkflowService,
) -> WorkflowCommandOutput:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return WorkflowCommandOutput(stdout="", stderr=str(exc), exit_code=2)
    try:
        _reject_context_flags(argv)
    except ValueError as exc:
        return WorkflowCommandOutput(stdout="", stderr=str(exc), exit_code=2)
    stderr = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr):
            args = build_workflow_parser().parse_args(argv)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 2
        return WorkflowCommandOutput(
            stdout="",
            stderr=_parse_error_with_help_hint(stderr.getvalue() or str(exc), argv),
            exit_code=exit_code,
        )
    session = session_factory()
    try:
        return _dispatch_workflow_command(
            args,
            context=context,
            session=session,
            service=service,
        )
    except ValueError as exc:
        return WorkflowCommandOutput(stdout="", stderr=str(exc), exit_code=2)
    finally:
        _close_session(session)


def _dispatch_workflow_command(
    args: argparse.Namespace,
    *,
    context: WorkflowCommandContext,
    session: Session,
    service: WorkflowService,
) -> WorkflowCommandOutput:
    if args.group == "inspect":
        return _handle_inspect(args, context=context, session=session, service=service)
    raise ValueError(f"unsupported workflow command group: {args.group}")


def _handle_inspect(
    args: argparse.Namespace,
    *,
    context: WorkflowCommandContext,
    session: Session,
    service: WorkflowService,
) -> WorkflowCommandOutput:
    if args.action == "resource-list":
        resources = service.list_resources(
            session,
            sample_id=context.sample_id,
            task_id=context.task_id,
            scope=args.scope,
            kind=args.kind,
            max_depth=args.max_depth,
            limit=args.limit,
        )
        return _format_output(
            {"resources": [_dump(resource) for resource in resources]},
            text_lines=[
                f"{resource.resource_id} {resource.kind} {resource.name} "
                f"task={resource.task_slug or '-'} bytes={resource.size_bytes}"
                for resource in resources
            ],
            output_format=args.format,
        )
    if args.action == "resource-content":
        resource_id = UUID(args.resource_id)
        content = service.read_resource_bytes(
            session,
            sample_id=context.sample_id,
            resource_id=resource_id,
            max_bytes=args.max_bytes,
        )
        if args.format == "json":
            return _format_output({"content": content.decode(errors="replace")}, [], "json")
        return WorkflowCommandOutput(stdout=content.decode(errors="replace"))
    if args.action == "task-tree":
        parent = UUID(args.parent_task_id) if args.parent_task_id else None
        deadline = time.monotonic() + max(args.wait_seconds, 0)
        tasks = service.list_tasks(session, sample_id=context.sample_id, parent_task_id=parent)
        while args.wait_seconds > 0 and time.monotonic() < deadline:
            children = [task for task in tasks if task.parent_task_id == context.task_id]
            if children and all(
                task.status in {"completed", "failed", "cancelled"} for task in children
            ):
                break
            time.sleep(2)
            tasks = service.list_tasks(session, sample_id=context.sample_id, parent_task_id=parent)
        return _format_output(
            {"tasks": [_dump(task) for task in tasks]},
            text_lines=[
                f"{'  ' * task.level}{task.task_slug} {task.status} {task.task_id}"
                for task in tasks
            ],
            output_format=args.format,
        )
    if args.action == "task-dependencies":
        deps = service.list_dependencies(
            session,
            sample_id=context.sample_id,
            task_id=context.task_id,
            direction=args.direction,
        )
        return _format_output(
            {"dependencies": [_dump(dep) for dep in deps]},
            text_lines=[
                f"{dep.source.task_slug} -> {dep.target.task_slug} status={dep.edge_status}"
                for dep in deps
            ],
            output_format=args.format,
        )
    if args.action == "next-actions":
        actions = service.get_next_actions(
            session,
            sample_id=context.sample_id,
            task_id=context.task_id,
            manager_capable=args.manager_capable,
        )
        return _format_output(
            {"next_actions": [_dump(action) for action in actions]},
            text_lines=[action.summary for action in actions],
            output_format=args.format,
        )
    raise ValueError(f"unsupported inspect action: {args.action}")


def _format_output(
    payload: JsonObject,
    text_lines: list[str],
    output_format: str,
) -> WorkflowCommandOutput:
    if output_format == "json":
        return WorkflowCommandOutput(stdout=json.dumps(payload, indent=2, sort_keys=True))
    return WorkflowCommandOutput(stdout="\n".join(text_lines))


def _dump(value: BaseModel | JsonObject) -> JsonObject:
    if isinstance(value, BaseModel):
        return cast(JsonObject, value.model_dump(mode="json"))
    if isinstance(value, dict):
        return value
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _close_session(session: Session) -> None:
    session.close()


def _reject_context_flags(argv: list[str]) -> None:
    if any(arg in _FORBIDDEN_CONTEXT_FLAGS for arg in argv):
        raise ValueError("scope/context flags are injected by the worker and cannot be supplied")


def _parse_error_with_help_hint(stderr: str, argv: list[str]) -> str:
    command_path = _help_command_path(argv)
    hint = f"Run '{command_path} --help' for more info."
    text = stderr.strip()
    if hint in text:
        return text
    return f"{text}\n{hint}" if text else hint


def _help_command_path(argv: list[str]) -> str:
    path = ["workflow"]
    for arg in argv:
        if arg.startswith("-"):
            break
        path.append(arg)
    return " ".join(path)
