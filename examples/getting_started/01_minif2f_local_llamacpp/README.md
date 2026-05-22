# MiniF2F With Local llama.cpp

Run three MiniF2F Lean proof tasks with llama.cpp and the E2B Lean sandbox.

## Prerequisites

- Python 3.13 and `uv`
- Ergon installed from this repository
- `E2B_API_KEY` in `.env` or your shell environment
- The MiniF2F Lean E2B template available to your E2B account
- `llama-server` on `PATH`
- A local GGUF model path or Hugging Face GGUF model reference

On macOS, install the llama.cpp server binary with:

```bash
brew install llama.cpp
```

If `llama-server` is installed somewhere else, pass its path with
`--llama-server-bin`.

## Recommended Run

From the repository root, pass a Hugging Face GGUF reference in
`<repo-id>:<filename.gguf>` form. The command downloads the model if needed,
starts `llama-server`, launches the run, and cleans up the server when it exits.

```bash
uv run ergon examples run minif2f-local-llamacpp \
  --base-model unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf \
  --limit 3
```

A local GGUF path also works:

```bash
uv run ergon examples run minif2f-local-llamacpp \
  --base-model /path/to/model.gguf \
  --limit 3
```

Useful options:

- `--model-cache-dir /tmp/ergon-models` changes the download cache.
- `--llama-server-bin /path/to/llama-server` uses a non-`PATH` server binary.
- `--keep-llama-server` leaves the managed server running after the command.

## Already Running Server

If you already have a llama.cpp OpenAI-compatible server listening locally, use
`--base-url` instead:

```bash
llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 8080
uv run ergon examples check minif2f-local-llamacpp --base-url http://localhost:8080
uv run ergon examples run minif2f-local-llamacpp \
  --base-url http://localhost:8080 \
  --limit 3
```

## Read Or Edit The Script

The CLI is a wrapper around the Python script. Run it directly when you want to
read or modify the benchmark authoring path:

```bash
uv run --project examples python examples/getting_started/01_minif2f_local_llamacpp/run.py
```

Defaults:

- `ERGON_LLAMA_CPP_BASE_URL=http://localhost:8080`
- `ERGON_LLAMA_CPP_MODEL` unset, so Ergon discovers the served model from `/v1/models`
- `ERGON_MINIF2F_LIMIT=3`
- `ERGON_MINIF2F_MAX_ITERATIONS=12`

You can override the same values on the command line:

```bash
uv run --project examples python examples/getting_started/01_minif2f_local_llamacpp/run.py \
  --limit 3 \
  --base-url http://localhost:8080 \
  --model local-proof-model \
  --max-iterations 12
```

`--model` is the model name served by llama.cpp. Use `--model-target` only when
you intentionally want to pass a full Ergon model target such as
`openai-compatible:http://router:9000#served-model`.

## What It Does

The script:

1. Resolves the model path or server URL.
2. Checks `E2B_API_KEY` and the llama.cpp endpoint.
3. Builds and persists a `MiniF2FBenchmark`.
4. Launches a run.
5. Prints the definition id, run id, model target, and observation commands.

MiniF2F is a real theorem-proving benchmark. Local model quality, quantization,
and context length strongly affect proof success. A terminal run with failed
proofs is still an honest first-run outcome: inspect the attempts, proof files,
tool calls, and evaluator feedback before changing models or iteration limits.

## Common Setup Problems

- Missing `E2B_API_KEY`: add it to Ergon's `.env` file or process environment.
- Hugging Face download failure: check the `--base-model` repo/file ref, network
  access, and disk space in the model cache directory.
- Unreachable llama.cpp server: start `llama-server` and verify
  `GET http://localhost:8080/v1/models` returns a model id.
- Missing MiniF2F Lean template or E2B provisioning failure: build/pin the
  template with `uv run ergon benchmark setup minif2f`, then retry.
- Model tool-call incompatibility: try a model and prompt configuration that can
  use OpenAI-compatible tool calls, or inspect the run artifacts for the failed
  attempts.

Do not treat theorem failures as setup failures. A run that launches all tasks
and records failed proof attempts is still useful evidence about the model,
context length, and iteration budget.
