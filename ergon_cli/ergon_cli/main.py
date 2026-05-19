"""Ergon CLI entry point."""

import asyncio
import sys

from ergon_cli.app import build_parser, dispatch


async def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return await dispatch(args, parser)


def main(argv: list[str] | None = None) -> int:
    coroutine = _main(argv)
    return asyncio.run(coroutine)  # slopcop: ignore[no-async-from-sync] -- CLI entrypoint


if __name__ == "__main__":
    sys.exit(main())
