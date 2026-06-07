"""Compatibility entrypoint for the MiniF2F getting-started example."""

from __future__ import annotations

import importlib

main = importlib.import_module("getting_started.01_minif2f_local_llamacpp.submit").main


if __name__ == "__main__":
    raise SystemExit(main())
