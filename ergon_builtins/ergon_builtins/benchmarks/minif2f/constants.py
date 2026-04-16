"""Shared constants for the MiniF2F benchmark."""

# The ergon-minif2f-v1 template exposes elan via /usr/local/bin symlinks, so no
# PATH export is needed. We cd into the mathlib project and invoke `lake env
# lean` so mathlib4 imports resolve against the cached oleans.
LEAN_CMD_PREFIX = "cd /tools/mathlib_project &&"
LEAN_CMD = "lake env lean"
