# Getting Started Examples

Small examples for running Ergon from a local checkout. Start here when you
want to launch a real run before writing your own benchmark script.

## Available Examples

| Example | What it runs |
| --- | --- |
| [`01_minif2f_local_llamacpp`](01_minif2f_local_llamacpp/) | Three MiniF2F Lean proof tasks with llama.cpp and an E2B Lean sandbox |

Use the CLI for the normal path:

```bash
uv run ergon examples list
uv run ergon examples info minif2f-local-llamacpp
uv run ergon examples check minif2f-local-llamacpp --base-url http://localhost:8080
```

The examples are still plain Python scripts. Read the script when you want to
see the object-bound benchmark authoring path directly.
