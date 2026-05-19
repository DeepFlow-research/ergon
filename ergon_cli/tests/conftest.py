"""Test bootstrap for package-local Ergon CLI tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOTS = (
    ROOT / "ergon_cli",
    ROOT / "ergon_core",
    ROOT / "ergon_builtins",
    ROOT / "ergon_ingestion",
)

for package_root in PACKAGE_ROOTS:
    package_root_str = str(package_root)
    if package_root_str not in sys.path:
        sys.path.insert(0, package_root_str)
