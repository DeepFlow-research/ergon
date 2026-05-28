from pathlib import Path

from ergon_builtins.environments.catalog import environment_cli_metadata


def sandbox_template_for(slug: str) -> Path:
    metadata = environment_cli_metadata()[slug]
    if metadata.sandbox_template is None:
        raise KeyError(slug)
    return metadata.sandbox_template


def setup_environment_slugs() -> tuple[str, ...]:
    return tuple(
        sorted(
            slug
            for slug, metadata in environment_cli_metadata().items()
            if metadata.sandbox_template is not None
        )
    )
