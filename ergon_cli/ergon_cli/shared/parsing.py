from uuid import UUID

from ergon_cli.shared.errors import CliUsageError


def parse_uuid(value: str, *, field_name: str = "UUID") -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise CliUsageError(f"{field_name} must be a valid UUID: {value}") from exc
