---
status: open
opened: 2026-09-14
fixed_pr: null
priority: P2
invariant_violated: docs/architecture/cross_cutting/artifacts.md
related_rfc: docs/rfcs/active/2026-09-07-manager-gym-port/
---

# Lost E2B upload response fails completed MAG work

## Symptom and evidence

On v12 (`5f74ceff`), supply-chain sample
`6ef32205-d4c9-4ff3-9142-7fbd6fc334fb` failed native task
`e52c98bd-54ea-4554-82ac-5391aa769177`, attempt
`fca0b077-effe-4ef9-89e9-c56eee6e80fd`, at
2026-09-14 13:28:43 UTC. Inference had been checkpointed and its context yielded.
The subsequent `MAGHumanWorker` resource upload raised `httpx.ReadError` in
`E2BSandboxRuntime.write_file` through the SDK's filesystem HTTP POST. The
attempt retained its traceback and no successful WorkerOutput. It remains an
infrastructure failure; it is not reclassified as a model failure.

The underlying network cause and whether that particular upload committed
are unknown. The installed SDK directly propagates this read error and documents
that writing the same file overwrites its complete contents. Native worker and
task retries are deliberately disabled to avoid repeating arbitrary side effects.

The acceptance runner also stopped early only in its pilot stage. The catalog
admission process was explicitly stopped at 13:31 UTC after diagnosis, leaving
the two active episodes to finish. No API worker or active sandbox was restarted.

## Repair and scope

The existing E2B builtin retries only file-upload `httpx.ReadError`, with three
total attempts and one/two-second waits. Each upload uses the original path and
identical immutable bytes. Exhaustion and all other exceptions propagate normally.
No command, inference, whole worker, scheduler or sandbox creation is retried.
The acceptance runner applies its admission-stop rule to every stage, including
unaccounted failures before the current manager has finished draining.

## Verification

`test_e2b_runtime.py` simulates a response lost after the remote write committed,
checks exact retained bytes, bounds persistent failure and preserves unrelated
errors. `test_acceptance.py` exercises early stop, drain and resume for both
pilot and catalog stages. The focused ten tests pass.

The real E2B proof uploaded 65,536 binary bytes, deliberately lost the first
successful upload's response, then verified the identical second upload and
readback. It made no model calls and closed sandbox `isctuf068iisqpoqamkuq`.
See the curated implementation receipt `upload-retry-v14.json`.
Fresh full acceptance against the repaired build remains required.
