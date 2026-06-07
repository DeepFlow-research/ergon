import argparse

from ergon_cli.domains.environments.commands import handle_environment


def register_environment_parser(subparsers: argparse._SubParsersAction) -> None:
    env = subparsers.add_parser("environment", help="Environment operations")
    env.set_defaults(handler=handle_environment)
    env_sub = env.add_subparsers(dest="env_action")
    env_sub.add_parser("list", help="List available environments")
    setup = env_sub.add_parser("setup", help="Build sandbox template for an environment")
    setup.add_argument("slug")
    setup.add_argument("--force", action="store_true")
