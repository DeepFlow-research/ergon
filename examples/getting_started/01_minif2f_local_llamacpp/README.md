# MiniF2F With Local llama.cpp

Run three MiniF2F Lean proof tasks with a local llama.cpp server and the E2B
Lean sandbox.

## Prerequisites

- Python 3.13 and `uv`
- The Ergon stack installed and configured
- `E2B_API_KEY` set for sandbox creation
- The MiniF2F Lean E2B template available to your E2B account
- A llama.cpp OpenAI-compatible server listening locally

Start llama.cpp in a separate terminal with your own GGUF model path:

```bash
llama-server --model /path/to/model.gguf --host 127.0.0.1 --port 8080
```

## Run

From the repository root:

```bash
export E2B_API_KEY=...
uv run python examples/getting_started/01_minif2f_local_llamacpp/run.py
```

The script defaults to:

- `ERGON_LLAMA_CPP_BASE_URL=http://localhost:8080`
- `ERGON_LLAMA_CPP_MODEL` unset, so Ergon discovers the served model from `/v1/models`
- `ERGON_MINIF2F_LIMIT=3`
- `ERGON_MINIF2F_MAX_ITERATIONS=12`

You can override the same values on the command line:

```bash
uv run python examples/getting_started/01_minif2f_local_llamacpp/run.py \
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

1. Checks `E2B_API_KEY` and `GET /v1/models` on the llama.cpp server.
2. Builds `MiniF2FBenchmark(limit=3, worker_factory=make_worker)`.
3. Binds `make_minif2f_worker(model="llamacpp:<base-url>", max_iterations=12)`.
4. Persists the benchmark definition with `persist_benchmark`.
5. Launches a run with `launch_run`.
6. Prints the definition id, run id, model target, and observation commands.

MiniF2F is a real theorem-proving benchmark. Local model quality, quantization,
and context length strongly affect proof success. A terminal run with failed
proofs is still an honest first-run outcome: inspect the attempts, proof files,
tool calls, and evaluator feedback before changing models or iteration limits.
