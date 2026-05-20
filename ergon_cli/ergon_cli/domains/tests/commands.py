from argparse import Namespace

from ergon_cli.domains.tests.models import TestCommand
from ergon_cli.domains.tests.service import run_test_command

SMOKE_TARGETS = frozenset({"full", "researchrubrics", "minif2f", "swebench-verified"})


def handle_test(args: Namespace) -> int:
    test_suite, raw_extra_args = _normalize_smoke_target(args)
    dry_run, extra_args = _normalize_args(args.dry_run, tuple(args.extra_args or ()))
    return run_test_command(
        TestCommand(
            domain=args.test_domain,
            suite=test_suite,
            dry_run=dry_run,
            extra_args=tuple(raw_extra_args) + extra_args,
        ),
        emit=print,
    )


def _normalize_smoke_target(args: Namespace) -> tuple[str, tuple[str, ...]]:
    if args.test_domain != "smoke" or args.test_suite in SMOKE_TARGETS:
        return args.test_suite, ()
    if args.test_suite.startswith("-"):
        return "full", (args.test_suite,)
    return args.test_suite, ()


def _normalize_args(dry_run: bool, extra_args: tuple[str, ...]) -> tuple[bool, tuple[str, ...]]:
    normalized = list(extra_args)
    if "--dry-run" in normalized:
        dry_run = True
        normalized = [arg for arg in normalized if arg != "--dry-run"]
    if normalized[:1] == ["--"]:
        normalized = normalized[1:]
    return dry_run, tuple(normalized)
