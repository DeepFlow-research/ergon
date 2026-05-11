"""Process bootstrap for local CLI/API component catalogs."""

from ergon_builtins.registry import register_builtins
from ergon_core.api.registry import registry
from ergon_core.core.persistence.shared.db import get_session


def register_and_publish_builtins() -> None:
    """Register builtins in-process and publish their import refs to the DB."""

    register_builtins(registry)
    with get_session() as session:
        registry.publish(session)
        session.commit()
