"""Export dashboard Inngest event contracts as JSON Schema.

Reads ergon-dashboard/src/generated/events/schemas/manifest.json, imports each
listed pydantic model from ergon_core.core.dashboard.event_contracts, and
writes its JSON schema next to the manifest. Downstream, json-schema-to-zod
turns these into the dashboard's Zod validators (see package.json's
generate:contracts:events step).

Usage:
    PYTHONPATH=. python scripts/export_contract_schemas.py
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = REPO_ROOT / "ergon-dashboard" / "src" / "generated" / "events" / "schemas"
MANIFEST_PATH = SCHEMA_DIR / "manifest.json"
CONTRACTS_MODULE = "ergon_core.core.dashboard.event_contracts"


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    module = importlib.import_module(CONTRACTS_MODULE)

    for entry in manifest:
        model_name = entry["modelName"]
        schema_file = entry["schemaFile"]
        model = getattr(module, model_name, None)
        if model is None:
            raise RuntimeError(
                f"Model {model_name!r} not found in {CONTRACTS_MODULE} "
                f"(manifest entry for event {entry['eventName']!r})"
            )

        schema = model.model_json_schema()
        missing = [key for key in ("title", "properties") if key not in schema]
        if missing:
            raise RuntimeError(
                f"JSON schema for {model_name} is missing expected keys {missing}; "
                f"pydantic output shape may have drifted"
            )

        out_path = SCHEMA_DIR / schema_file
        out_path.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n")
        print(f"wrote {out_path} ({len(schema['properties'])} properties)")


if __name__ == "__main__":
    main()
