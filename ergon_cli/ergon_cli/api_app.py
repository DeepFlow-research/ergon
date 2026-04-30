"""Local API composition target with builtins and smoke fixtures published."""

from importlib import import_module

from ergon_builtins.registry import register_builtins
from ergon_core.api.registry import registry
from ergon_core.core.persistence.shared.db import ensure_db, get_session
from tests.fixtures.smoke_components import register_smoke_components

ensure_db()
register_builtins(registry)
register_smoke_components(registry)
with get_session() as session:
    registry.publish(session)
    session.commit()

app = import_module("ergon_core.core.rest_api.app").app
