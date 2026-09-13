# MAG pre-port proof — 13 September 2026

**The proof found blockers before the port started. Broad implementation is not ready.** No production code was changed. The additions are reproducible probes, a deterministic worker/criterion fixture, and evidence. The next implementation slice should fix and recheck the observed boundaries before introducing the MAG agents or importing the full scenario catalog.

The working checkout is based on Ergon `6910ecfc74807209b86db5c6f063ac9932b462a0` and has pre-existing changes; this is not a claim about a clean upstream release. [Provenance](provenance.json) records relevant file hashes and installed versions. The prior source inventory remains separate from this runtime proof.

**Deployment parity gap:** the current Dockerfile installs each package independently without the workspace lock. The local probes used Inngest 0.5.18 / E2B 2.20.0 / PydanticAI 1.87.0; the Linux API used 0.5.19 / 2.49.1 / 2.31.1 respectively. The missing E2B close method was observed in both environments. Other component/replay and model results must not be assumed identical across them. Fix the image's dependency installation and rerun against the chosen deployed versions before accepting the proof gate.

## Live results

| Boundary | Experiment and observed result | Consequence |
|---|---|---|
| Standing Qwen | `qwen3-8-27b-28` health returned 200. Through a direct PydanticAI/OpenAI provider it called `read_fatigue("alice")` once and returned the exact typed result. Two successful inference requests used 863 input and 71 output tokens. | A standing internal endpoint and compatible tool/structured-output path exist. This does not prove role quality, rubric fidelity, largest-prompt capacity or a pinned immutable checkpoint. |
| Ergon model resolver | The existing resolver, even with an explicit correct credential and model ID, returned 404. It adds `/v1` after the gateway's complete model base URL. Both attempted model-discovery routes also returned 404. | Fix routing/configuration in the existing builtins provider. Normal worker/judge callers also need a configured secret reference: they currently call the resolver without its optional `api_key` argument. Do not put keys in task snapshots or add another model-serving system. |
| E2B cross-process access | Native provision, writing, reconstruction by sandbox ID in a separate process, reading and writing back all worked. | Reuse the existing E2B backend and native task-bound sandbox lifecycle. No local filesystem execution backend or new shared-environment runtime is justified. |
| E2B read contract | A text file read returned `str`, although Ergon declares `bytes`. | Repair the existing E2B runtime's read mode and verify binary data too. The text artifact publisher happened to succeed; that does not establish binary correctness. |
| E2B detach | Native `detach()` raised `AttributeError`: `AsyncSandbox` has no `close`. | A concrete compatibility fix belongs in `ergon_builtins/sandbox/e2b_runtime.py`, preserving the distinction between local detach and remote termination. No core cleanup rewrite is justified by this observation. |
| Full native task | Used `Experiment.submit` through real Inngest and PostgreSQL in local Linux containers, with real E2B. A deterministic Worker wrote the artifact, its full output/actor metadata persisted, the artifact published, and the native Rubric scored 1.0. **The sample and attempt then failed**, with the missing `AsyncSandbox.close` error. | Do not accept a score, a worker result or stack health as end-to-end success. Re-run this same task after the backend fix and require a completed sample, correct artifact, evaluation and verified terminal cleanup. This was not an AWS VM or a MAG sample. |
| Concurrent native messages | Two threads using separate PostgreSQL connections were synchronized after their native `max(sequence)` reads. Both writes succeeded with sequence **2**; the thread contains the seed plus both messages. | The existing communication owner needs transaction-safe sequencing. This is a forced interleaving on PostgreSQL 15.19, not a timing guess or SQLite approximation. |

Receipts: [Qwen](qwen-result.json), [E2B](e2b-result.json), [native task and evaluation](lifecycle-result.json), [PostgreSQL race](postgres-result.json), [final sandbox checks](cleanup-result.json).

Deployment discovery came from [the inference retirement notice](https://hcompany-groupe.slack.com/archives/C089LDR72GG/p1788182536857049), which says to replace `qwen38-27b-v2` with `qwen3-8-27b-28`. [The standing-capacity discussion](https://hcompany-groupe.slack.com/archives/C08C79HE737/p1788770888362679) supports reuse, but its replica counts are historical and were not used as current allocation evidence. The base URL came from the local HAI provider implementation and was verified with the live requests.

## Native component and replay results

[The focused probes](../../../../../../ergon_core/tests/unit/runtime/test_manager_gym_preport_proof.py) use real native services with SQLite, plus the installed Inngest SDK's mocked-trigger replay executor. Existing focused baseline tests: **25 passed**. New probes: **4 passed, 7 strict expected failures**. With expected-failure handling disabled, the same desired-contract checks produced **7 failures and 4 passes**. Expected failures document gaps; they are not acceptance passes. [Machine-readable test results](contracts-result.json) preserve test names and failure descriptions.

| Probe | Actual observation | Owner / interpretation |
|---|---|---|
| Dependency created before A completes | B is released when A completes. | Existing native scheduler works for this case. |
| Dependency created after A completes | B receives no immediate ready dispatch. | Native spawn/readiness integration; do not add a MAG scheduler. |
| Explicitly cancelled dependent | Completing its prerequisite reactivates it. | Native lifecycle must preserve cancellation cause. |
| Description refinement | Graph description changes; reconstructed executable Task keeps the old description. | Existing mutation owner must update the executable snapshot atomically. |
| Attempt preparation | Calling native prepare for B creates an attempt while A remains incomplete. | Claim boundary lacks a prerequisite recheck. This is a service-boundary test, not a reproduced live stale-event race. |
| Two people of one Worker class | Alice and Bob receive the same class-derived assignment slug. | A required actor-identity capability, not a claim that current documented type identity is itself a bug. Existing context records already accept a separate binding key. |
| Uncheckpointed policy before native spawn | Synthetic policy side effect executes **five times** for one decision, while exactly **one** child node is persisted. | Native spawning already deduplicates its own work. The surrounding policy needs durable handling. No actual LLM was called in this test. |
| Same policy inside existing `ctx.step.run` | One policy execution and one child. | A separate Task/E2B sandbox per decision is **not proven necessary**. Test a narrow native Worker-facing checkpoint/continuation boundary before selecting that more expensive composition. The public WorkerContext does not currently expose this capability. |
| Full output and actor context | Full 3,000-character output and metadata round-trip; an `alice` context binding persists. | Reuse the existing output repository and context columns. No new output store or context schema. |
| Retrying a message request | Two distinct rows. | Characterization of the current API, which has no action-idempotency contract. Add action-key deduplication to the existing owner if the selected retry semantics require it. |
| Judge exception | The existing failure persistence path writes score 0. | The proposed incomplete/null policy requires an explicit contract change. A product decision, not a defect against the current zero-score policy. |

## What the next proof slice must settle

1. Fix the existing E2B adapter, existing provider configuration and Docker dependency parity, then rerun the native task and run the bounded Qwen probe **through ordinary Worker and judge callers**. Verify cleanup after success and failure separately. Today the live Qwen and E2B/native-task probes are separate experiments.
2. Exercise a minimal manager → native child → durable wait → manager continuation through real Inngest, including streamed context, a restart/retry, stable model-call count and one committed action. Compare the existing-step approach before accepting one decision Task and sandbox per turn. The SDK test establishes the risk and a possible primitive, not the final manager design.
3. Fix native late-dependency/refinement/cancellation/claim behavior and message ordering/idempotency with boundary tests. Use PostgreSQL for pending-edit/claim races and cancellation races; the SQLite reproductions do not prove those fixes will be transactional.
4. Define person identity without changing what `assigned_worker_slug` means for existing users. Verify Alice/Bob assignment, workload queries and actor views together; do not infer the final schema from the identity xfail.
5. Once those pass, run one scripted MAG episode with a real human-worker state read, a stakeholder exchange, native child work and a frozen source-rubric evaluation. Only then expand the catalog. This proof has not implemented or validated fatigue, clock semantics, all 13 actions or MAG rubric fidelity.
6. Confirm the outstanding benchmark choices in R2–R8 of the main plan. A runtime probe cannot choose clock/stopping behavior, source-quirk corrections or judge policy for Charlie.

The user AC also still needs the actual small Linux VM in the training account, serving provenance/available capacity, role routing, representative prompt sizes, autonomous samples and full catalog evidence. Local Linux containers establish a useful boundary but do not satisfy the VM acceptance condition. No VM or GPU replica was provisioned or modified here. Reuse avoided new serving allocation; actual E2B/account charges were not measured and are not asserted to be zero.

## Reproduction and containment

Run from the repository root with its locked environment. Unit probes do not need infrastructure:

```bash
ergon test core unit -- -k preport -n 0 -rx --timeout=30
ergon test core unit -- -k preport -n 0 -rx --runxfail --timeout=30
```

The second command intentionally returns failure on the current implementation. Live probes are standalone evidence scripts, not a second benchmark runner. They require the configured E2B credential, and Qwen requires `HAI_API_KEY` or `MAG_PROOF_SECRET_FILE` pointing to a local dotenv secret source. They never write credential values to receipts.

The native lifecycle run used the normal `ergon start` command under isolated Compose project `ergon-mag-proof`, with its own PostgreSQL volume. The proof fixture is [tests/fixtures/mag_preport.py](../../../../../../tests/fixtures/mag_preport.py). Run `lifecycle_probe.py` with repository root on `PYTHONPATH`, then `postgres_probe.py` against that proof sample. E2B canaries have a 300-second sandbox limit and explicit final termination. The lifecycle receipt's `cleanup_check` was performed by the proof harness; it alone does not prove autonomous cleanup. The separate final receipt verifies all three created sandbox IDs are no longer running.

Do not repeatedly launch live probes to get a green result without changing the failing boundary. Keep the failed evidence when rerunning. The passing criterion deliberately accepts both text and bytes to expose later lifecycle behavior; it does not mask the separately recorded byte-contract failure.

The proof containers and network have been removed. The isolated `ergon-mag-proof_postgres_data` volume remains for inspection; no running proof services remain. Probe Python files pass Ruff lint/format checks; local document links and all 85 manifest IDs were checked.
