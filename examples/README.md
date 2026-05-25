# Ergon Examples

This directory contains runnable examples for learning Ergon from plain Python.
It is also an installable `ergon-examples` workspace project, so scripts can
import shared example helpers and Ergon packages without mutating `sys.path`.

Start with [`getting_started/`](getting_started/). Those examples are intentionally
small, but they exercise the same object-bound APIs used by larger benchmarks:
configure a benchmark object, bind workers and sandboxes, persist the definition,
launch a sample, and inspect the resulting artifacts.
