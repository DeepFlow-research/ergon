# Native MA-Gym implementation acceptance

Status: live acceptance in progress. This is not yet a completed 20-scenario result.

The implementation runs the pinned MAG catalog through native Ergon workers,
PostgreSQL graph/attempt/message/resource records, Inngest task propagation,
E2B task sandboxes and ordinary evaluator jobs. The training-account VM hosts
Ergon services; all model roles use the standing internal Qwen deployment.

The authoritative scope and annotated code map are in
[the implementation record](../../../../../superpowers/plans/2026-09-07-manager-gym-native-port.md).
[The operating runbook](../../../../../../examples/manager_gym/README.md)
contains reproduction, continuation, evidence export and cleanup commands.

## Build and profile

- Upstream MAG: `3f7a5d4af1d31abaedbedd525a0090452926fef4`.
- Ergon base: `6910ecfc74807209b86db5c6f063ac9932b462a0`.
- Native execution digest: `0bd62a9743347179d5303a7236ccdb595bbcefcbbff788306f4066683d8c20af`.
- Profile: `mag-native-v1`, CoT manager, seed 0, 50 decisions, two concurrent samples.
- Internal model: `qwen3-8-27b-28`; request maximum 32,768 output tokens,
  verified 2,048-token thinking cap, 300-second request and 600-second operation limits.
- E2B lifetime: 3,600 seconds; manager decision wall budget 2,400 seconds;
  shared admitted-work drain 600 seconds; serial grading must fit the remaining lifetime.
- CPU VM: training account, Ubuntu 24.04, m6i.xlarge, 4 vCPU/16 GiB,
  encrypted 100 GiB gp3; no additional model replicas or GPUs provisioned.

[Standing model provenance](standing-model.json),
[thinking-budget probe](thinking-budget-probe.json), and
[VM provenance](training-vm.json) record nonsecret deployment details.
The serving image and weight location were observed; immutable weight bytes
were not independently identified. Standing inference is reused, but CPU/EBS/E2B
billing has not been established as zero. Simulated wages are benchmark metrics.

## Verified before catalog acceptance

- Full Python unit suite: **1,006 passed**, one skipped, one expected failure.
  The expected failure demonstrates why uncheckpointed policy code reexecutes
  on workflow replay; it is not an unimplemented port requirement.
- Full PostgreSQL/Inngest integration suite: **45 passed**, including concurrent
  message ordering, nonblocking graph row locks, repeatable migrations and
  cancellation-cause-aware restart propagation.
- Dashboard: **136 unit tests passed**, type checking and lint passed.
  A real failed sample was opened and its evaluation displayed **Incomplete**.
- Ruff lint/format, type checking, complexity and inline suppression budget pass.
  Slopcop passes with zero errors; it reports 661 warnings, compared with 485 on the clean base.
  Narrow per-file rule exceptions preserve pinned source scoring/fallback semantics;
  they do not exempt the native manager/worker/transport/rubric adapters or core.
- Build-v5 delayed cancellation probe:
  `ec5dc9fe-12ee-4c7f-9f14-31c59913cf7e` passed all checks. Both running task
  attempts were cancelled, both E2B sandboxes closed, and no delayed child appeared.
  [Receipt](delayed-cancellation.json).
- Build-v5 scripted native composition contract:
  `f0a7096a-68a4-4299-bf75-d91e7bbf62e1` passed with score 1.0. Seven nodes,
  six completed attempts, one intentional pending cancellation, five messages,
  42 retained artifacts (including checkpoint results) and verified sandbox closure.
  This is a contract score, not an autonomous MAG utility result.
- Frozen-snapshot reevaluation:
  `052644bc-f7be-4053-bf08-51a1d6512ba4` passed all checks against the accepted
  build-v4 legal snapshot. One native task, no work reexecution, the same snapshot
  hash, all 48 criteria, recomputed utility and closed E2B sandbox.
  Its utility was 0.6615606281 versus 0.6400869439 on the source evaluation;
  unchanged evidence does not guarantee deterministic model grading.
  [Receipt](frozen-reevaluation.json).

## Defects found and corrected during live proofs

1. A blocking PostgreSQL graph lock froze the event loop. The existing native
   repository now acquires its sample lock without blocking the event loop and
   uses a lock mode compatible with dependent foreign-key writes.
2. Qwen exhausted output tokens before producing structured output. A live
   provider probe verified the request-level thinking cap before enabling it.
3. Full documents were mistakenly fed into repeated manager observations and
   judge contexts. The pinned source uses bounded previews. Manager/judge
   resources now use 300 characters, AI/human inputs 200; full native evidence
   remains retained. Both affected exploratory pilots remain failed evidence.
4. A cancelled manager resumed later and spawned another child. Invoked workers
   now share native cancellation rules; spawning/claiming reject terminal state;
   late finalization preserves cancellation. Existing sample cleanup covers every
   owned attempt and lifecycle-recorded sandbox.
5. Attempts recorded sandbox IDs only after worker output. That write now happens
   before worker execution, so cancellation can find a sandbox during inference
   or durable waits. The live delayed-spawn probe checks beyond the old failure window.
6. An early resource mapping exposed unrelated workflow artifacts. Assignment now
   selects declared initial input IDs and adds completed native prerequisite outputs.
7. Implicit actor-order edges added during an early implementation were removed.
   Only authored task dependencies constrain work; human fatigue captures the exact
   completed attempt history visible at invocation start.

8. ICAAP and marketing exceeded Inngest's 32 MB aggregate state limit when full observations and
   inference results accumulated across checkpoints. The native worker checkpoint
   facade now retains results through SampleResourcePublishService and the existing
   blob store. Inngest holds a compact hash/size reference; replay verifies the
   retained bytes and fails on corruption or loss without repeating inference.
   The original failed samples are `d50be19e-a0a6-4c67-8523-e8e9caa0860c`
   and `8d82f2ac-ec79-4fd9-86d3-ba8546e88bd7`.

## Evidence and interpretation

Final autonomous pilot/catalog results, raw export digests and temporary VM
teardown receipt are pending. [Historical build-v4 results](historical-v4.json)
retain the accepted legal pilot and both checkpoint-limit failures.

Successful worker inference has native context transcripts and usage. Judge
records retain the evaluated prompt, score, feedback, settings and usage; they
are not claimed to contain a complete provider transcript. Usage lost before
an inference checkpoint is unavailable. Raw traces stay in the local evidence
archive; the review contains aggregate provenance and check results.

All 20 scenarios contain 1,230 selected terminal criteria (876 LLM, 354 callable),
from 1,281 packaged definitions. This profile covers decision indices 0–49;
seven scenarios have later timeline events. It establishes native integration,
not statistical equivalence, a full-timeline experiment or RL readiness.
