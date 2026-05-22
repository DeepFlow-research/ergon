# Getting Started Examples

These examples are the public first steps for running Ergon locally.

## Available Examples

| Example | What it runs |
| --- | --- |
| [`01_minif2f_local_llamacpp`](01_minif2f_local_llamacpp/) | Three MiniF2F Lean proof tasks with a local llama.cpp OpenAI-compatible server and E2B Lean sandbox |

The examples stay as plain Python scripts, and `uv run ergon examples ...`
provides a thin wrapper for listing, checking, and launching them. The script is
still the source of behavior, so you can read it directly to see the benchmark
authoring path.
