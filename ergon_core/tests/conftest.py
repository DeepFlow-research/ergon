"""Test bootstrap for package-local Ergon Core tests."""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOTS = (
    PACKAGE_ROOT,
    REPO_ROOT / "ergon_builtins",
)

for package_root in PACKAGE_ROOTS:
    package_root_str = str(package_root)
    if package_root_str not in sys.path:
        sys.path.insert(0, package_root_str)
