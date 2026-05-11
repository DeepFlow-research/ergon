"""Local API composition target with builtins and smoke fixtures published."""

from importlib import import_module

from ergon_builtins.registry import register_builtins
from ergon_core.core.persistence.shared.db import ensure_db

ensure_db()
register_builtins()

app = import_module("ergon_core.core.rest_api.app").app
