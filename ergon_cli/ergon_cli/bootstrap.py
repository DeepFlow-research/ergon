"""Process bootstrap for local CLI/API component catalogs."""

from ergon_builtins.registry import register_builtins


def register_and_publish_builtins() -> None:
    """Register process-local builtins."""

    register_builtins()
