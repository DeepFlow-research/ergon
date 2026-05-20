"""Ergon CLI entry point."""

import argparse
import asyncio
import sys

from ergon_cli.app import build_parser, dispatch


async def _main(argv: list[str] | None = None) -> int:
    parser, args = _parse_args(argv)
    return await dispatch(args, parser)


def _parse_args(
    argv: list[str] | None = None,
) -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    parser = build_parser()
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        if getattr(args, "command", None) != "test":
            parser.error(f"unrecognized arguments: {' '.join(unknown)}")
        args.extra_args = [*(getattr(args, "extra_args", None) or []), *unknown]
    return parser, args


def main(argv: list[str] | None = None) -> int:
    coroutine = _main(argv)
    return asyncio.run(coroutine)  # slopcop: ignore[no-async-from-sync] -- CLI entrypoint


if __name__ == "__main__":
    sys.exit(main())
