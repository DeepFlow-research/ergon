from argparse import Namespace

from ergon_cli.domains.environments.models import EnvironmentCommand
from ergon_cli.domains.environments.service import list_environment_rows
from ergon_cli.domains.environments.service import setup_environment as setup_environment_service
from ergon_cli.shared.output import render_table


async def handle_environment(args: Namespace) -> int:
    if args.env_action not in {"list", "setup"}:
        print("Usage: ergon environment {list|setup}")
        return 1
    values = vars(args)
    command = EnvironmentCommand(
        action=args.env_action,
        slug=values.get("slug"),
        force=values.get("force", False),
    )
    if command.action == "list":
        print(render_table(["Slug", "Name", "Description"], list_environment_rows()))
        return 0
    return setup_environment_service(command)
