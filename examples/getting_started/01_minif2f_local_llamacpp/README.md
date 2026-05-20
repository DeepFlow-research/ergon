# MiniF2F With Local llama.cpp

Run three MiniF2F Lean proof tasks with a managed local llama.cpp server and the
E2B Lean sandbox.

## Prerequisites

- Python 3.13 and `uv`
- The Ergon stack installed and configured
- `E2B_API_KEY` configured in Ergon's `.env` file or process environment
- The MiniF2F Lean E2B template available to your E2B account
- `llama-server` installed and available on `PATH`
- A local GGUF model path or Hugging Face GGUF model reference

On macOS, install the llama.cpp server binary with:

```bash
brew install llama.cpp
```

If `llama-server` is installed somewhere else, pass its path with
`--llama-server-bin`.

## Run

From the repository root, pass a Hugging Face GGUF reference in
`<repo-id>:<filename.gguf>` form. The example downloads the file into the model
cache, starts `llama-server`, waits for `/v1/models`, launches the MiniF2F run,
and cleans up the model server when the run command exits.

```bash
uv run ergon examples run minif2f-local-llamacpp \
  --base-model unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf \
  --limit 3
```

Downloaded models use `~/.cache/ergon/examples/models` by default. Use
`--model-cache-dir` or `ERGON_EXAMPLE_MODEL_CACHE_DIR` when you want a temporary
or shared cache location.

```bash
uv run ergon examples run minif2f-local-llamacpp \
  --base-model unsloth/DeepSeek-Prover-V2-7B-GGUF:Q4_K_M.gguf \
  --model-cache-dir /tmp/ergon-models \
  --limit 3
```

A local GGUF path also works:

```bash
uv run ergon examples run minif2f-local-llamacpp \
  --base-model /path/to/model.gguf \
  --limit 3
```

Use `--llama-server-bin` if the command is not on `PATH`, and
`--keep-llama-server` if you want to inspect or reuse the model server after the
example command exits.

```bash
uv run ergon examples run minif2f-local-llamacpp \
  --base-model /path/to/model.gguf \
  --llama-server-bin /path/to/llama-server \
  --keep-llama-server
```

## Already Running Server

If you already have a llama.cpp OpenAI-compatible server listening locally, use
the advanced path:

```bash
llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 8080
uv run ergon examples check minif2f-local-llamacpp --base-url http://localhost:8080
uv run ergon examples run minif2f-local-llamacpp \
  --base-url http://localhost:8080 \
  --limit 3
```

The plain Python script remains the source of benchmark behavior and is useful
when you want to read or edit the example directly:

```bash
uv run --project examples python examples/getting_started/01_minif2f_local_llamacpp/run.py
```

The script defaults to:

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

1. Resolves `--base-model` from either a local path or Hugging Face GGUF ref.
2. Starts `llama-server` for managed runs, then discovers the served model from `/v1/models`.
3. Checks Ergon settings for `E2B_API_KEY` and verifies the llama.cpp endpoint.
4. Builds `MiniF2FBenchmark(limit=3, worker_factory=make_worker)`.
5. Binds `make_minif2f_worker(model="llamacpp:<base-url>", max_iterations=12)`.
6. Persists the benchmark definition with `persist_benchmark`.
7. Launches a run with `launch_run`.
8. Prints the definition id, run id, model target, and observation commands.

MiniF2F is a real theorem-proving benchmark. Local model quality, quantization,
and context length strongly affect proof success. A terminal run with failed
proofs is still an honest first-run outcome: inspect the attempts, proof files,
tool calls, and evaluator feedback before changing models or iteration limits.

## Manual Readiness Notes

The automated tests for this example do not require a real llama.cpp server or
E2B account. They cover argument parsing, preflight failures, model-target
construction, and launch wiring with monkeypatched Ergon APIs.

When running against real services, these are expected setup or integration
failures rather than successful benchmark launches:

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

Do not treat theorem failures as setup failures. A run that launches all three
tasks and records failed proof attempts is still useful evidence about the local
model, context length, and iteration budget.
