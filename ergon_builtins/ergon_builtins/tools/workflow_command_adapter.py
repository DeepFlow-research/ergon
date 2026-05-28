import argparse
import contextlib
import io
import json
import shlex
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from ergon_builtins.tools.dynamic_task_factory import (
    CopyParentDynamicTaskFactory,
    DynamicTaskFactory,
)
from ergon_core.api import Task, WorkerContext
from ergon_core.core.application.runtime.errors import GraphError
from ergon_core.core.application.runtime.sample_lifecycle import WorkflowService
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.enums import SampleResourceKind
from ergon_core.core.shared.json_types import JsonObject

_RESOURCE_SCOPES = ("visible", "own", "input", "upstream", "children", "descendants")
_RESOURCE_KINDS = tuple(kind.value for kind in SampleResourceKind)
_OUTPUT_FORMATS = ("text", "json")
_DEPENDENCY_DIRECTIONS = ("upstream", "downstream", "both")
_FORBIDDEN_CONTEXT_FLAGS = {
    "--run-id",
    "--task-id",
    "--node-id",
    "--execution-id",
    "--sandbox-id",
    "--sandbox-task-key",
    "--environment-type",
}


class WorkflowCommandContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    sample_id: UUID
    task_id: UUID
    execution_id: UUID
    sandbox_task_key: UUID
    benchmark_type: str


class WorkflowCommandOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    stdout: str
    stderr: str | None = None
    exit_code: int = 0


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

    manage = sub.add_parser("manage")
    manage_sub = manage.add_subparsers(dest="action", required=True)
    add_subtask = manage_sub.add_parser("add-subtask")
    add_subtask.add_argument("--task-slug", required=True)
    add_subtask.add_argument("--description", required=True)
    add_subtask.add_argument("--depends-on", action="append", default=[])
    add_subtask.add_argument("--format", choices=_OUTPUT_FORMATS, default="text")

    return parser


async def execute_workflow_command(
    command: str,
    *,
    context: WorkflowCommandContext,
    worker_context: WorkerContext,
    session_factory: Callable[[], Any] = get_session,
    service: WorkflowService | None = None,
    task_factory: DynamicTaskFactory | None = None,
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

    service = service or WorkflowService()
    task_factory = task_factory or CopyParentDynamicTaskFactory()
    try:
        with _session_scope(session_factory) as session:
            return await _dispatch_workflow_command(
                args,
                context=context,
                worker_context=worker_context,
                session=session,
                service=service,
                task_factory=task_factory,
            )
    except (GraphError, ValueError) as exc:
        return WorkflowCommandOutput(stdout="", stderr=str(exc), exit_code=2)


async def _dispatch_workflow_command(
    args: argparse.Namespace,
    *,
    context: WorkflowCommandContext,
    worker_context: WorkerContext,
    session: Session,
    service: WorkflowService,
    task_factory: DynamicTaskFactory,
) -> WorkflowCommandOutput:
    if args.group == "inspect":
        return _handle_inspect(args, context=context, session=session, service=service)
    if args.group == "manage":
        return await _handle_manage(
            args,
            context=context,
            worker_context=worker_context,
            session=session,
            task_factory=task_factory,
        )
    return WorkflowCommandOutput(
        stdout="",
        stderr=f"unsupported workflow command group: {args.group}",
        exit_code=2,
    )


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


async def _handle_manage(
    args: argparse.Namespace,
    *,
    context: WorkflowCommandContext,
    worker_context: WorkerContext,
    session: Session,
    task_factory: DynamicTaskFactory,
) -> WorkflowCommandOutput:
    if args.action != "add-subtask":
        raise ValueError(f"unsupported manage action: {args.action}")
    parent = await _load_parent_task(session, context=context, sandbox_id=worker_context.sandbox_id)
    task = task_factory.child_task(
        parent=parent,
        task_slug=args.task_slug,
        description=args.description,
    )
    depends_on = tuple(UUID(value) for value in args.depends_on)
    handle = await worker_context.spawn_task(task, depends_on=depends_on)
    return _format_output(
        {
            "spawned_task": {
                "task_id": str(handle.task_id),
                "task_slug": task.task_slug,
                "parent_task_id": str(context.task_id),
                "depends_on": [str(dep) for dep in depends_on],
            }
        },
        text_lines=[f"{task.task_slug} {handle.task_id}"],
        output_format=args.format,
    )


async def _load_parent_task(
    session: Session,
    *,
    context: WorkflowCommandContext,
    sandbox_id: str,
) -> Task:
    row = session.exec(
        select(SampleGraphNode).where(
            SampleGraphNode.sample_id == context.sample_id,
            SampleGraphNode.task_id == context.task_id,
        )
    ).one()
    if not row.task_json:
        raise ValueError(f"current task {context.task_id} has no object-bound task_json")
    return await Task.from_definition(
        cast(dict[str, Any], row.task_json),
        task_id=context.task_id,
        sandbox_id=sandbox_id,
    )


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


@contextlib.contextmanager
def _session_scope(session_factory: Callable[[], Any]) -> Iterator[Session]:
    session_or_context = session_factory()
    if isinstance(session_or_context, AbstractContextManager):
        with session_or_context as session:
            yield cast(Session, session)
        return

    try:
        yield cast(Session, session_or_context)
    finally:
        cast(Session, session_or_context).close()


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
