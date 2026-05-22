import argparse

from ergon_cli.domains.tests.commands import handle_test


def register_test_parser(subparsers: argparse._SubParsersAction) -> None:
    test = subparsers.add_parser("test", help="Run Ergon test suites")
    test.set_defaults(handler=handle_test)
    domain_sub = test.add_subparsers(dest="test_domain", required=True)

    list_parser = domain_sub.add_parser("list", help="List available test suites")
    list_parser.set_defaults(test_suite="list")
    list_parser.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    list_parser.add_argument("extra_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    smoke_parser = domain_sub.add_parser("smoke", help="Run canonical benchmark smoke tests")
    smoke_parser.add_argument(
        "test_suite",
        nargs="?",
        default="full",
        metavar="{full,researchrubrics,minif2f,swebench-verified}",
        help="Benchmark smoke target",
    )
    smoke_parser.add_argument(
        "--dry-run", action="store_true", help="Print command without running"
    )
    smoke_parser.add_argument("extra_args", nargs=argparse.REMAINDER, help="Extra args after --")

    _add_domain(
        domain_sub, "full", "Run suites across all applicable domains", ("unit", "smoke", "full")
    )
    _add_domain(domain_sub, "core", "Run core tests", ("unit",))
    _add_domain(domain_sub, "builtins", "Run builtins tests", ("unit",))
    _add_domain(domain_sub, "cli", "Run CLI tests", ("unit",))
    _add_domain(domain_sub, "ingestion", "Run ingestion tests", ("unit",))
    _add_domain(domain_sub, "dashboard", "Run dashboard tests", ("unit", "smoke"))
    _add_domain(
        domain_sub,
        "backend",
        "Run backend cross-package tests",
        ("integration", "smoke", "e2e"),
    )
    _add_domain(domain_sub, "real-llm", "Run real-LLM tests", ("full",))


def _add_domain(
    domain_sub: argparse._SubParsersAction,
    name: str,
    help_text: str,
    suites: tuple[str, ...],
) -> None:
    parser = domain_sub.add_parser(name, help=help_text)
    suite_sub = parser.add_subparsers(dest="test_suite", required=True)
    for suite in suites:
        suite_parser = suite_sub.add_parser(suite)
        suite_parser.add_argument(
            "--dry-run", action="store_true", help="Print command without running"
        )
        suite_parser.add_argument(
            "extra_args", nargs=argparse.REMAINDER, help="Extra args after --"
        )
