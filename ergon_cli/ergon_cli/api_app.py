"""Local API composition target."""

from importlib import import_module

from ergon_core.core.persistence.shared.db import ensure_db

ensure_db()
app = import_module("ergon_core.core.rest_api.app").app
