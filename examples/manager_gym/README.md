# Native Manager Agent Gym

One sample is one manager episode. The manager uses native task spawning,
dependencies, pending edits, messaging and evaluator jobs. AI, simulated human
and stakeholder work each run as normal Ergon tasks with their own E2B sandbox.
The Linux VM hosts Ergon's ordinary API, PostgreSQL, Inngest and dashboard.
Inference uses the existing training gateway; it does not run in E2B.

## Start on a Linux VM

The acceptance deployment uses Ubuntu 24.04, Python 3.13, Docker/Compose,
4 vCPU, 16 GiB RAM and an encrypted 100 GiB disk in the training account.
Use an SSH security group restricted to your address. Keep service ports
private; tunnel dashboard port 3001 if needed. No GPU or AWS instance role is
required. Provision through your existing VM workflow and record its resource
IDs so that cleanup only removes this deployment.

Populate an ignored, mode-600 `.env` using configured secret storage:

```dotenv
E2B_API_KEY=<configured E2B credential>
ERGON_OPENAI_COMPATIBLE_API_KEY=<configured training gateway credential>
COMPOSE_PROJECT_NAME=ergon-mag-acceptance
ERGON_API_IMAGE=ergon-mag-native:acceptance
```

Then run from the repository root:

```bash
uv sync --python 3.13 --frozen --no-dev --package ergon-cli
export COMPOSE_FILE=docker-compose.yml:examples/manager_gym/compose.acceptance.yml
uv run --no-sync ergon start
uv run --no-sync ergon doctor
```

The override disables API hot reload. Keep executable source fixed while
samples are running. The Docker image installs from `uv.lock`; secrets, local
virtual environments and data are excluded from its build context.

## Run and inspect

```bash
docker compose exec -T api python examples/manager_gym/preflight.py \
  --output /app/data/mag-acceptance/preflight.json
docker compose exec -T api python examples/manager_gym/cancellation.py \
  --output /app/data/mag-acceptance
docker compose exec -T api python examples/manager_gym/acceptance.py \
  --stage contract --output /app/data/mag-acceptance
docker compose exec -T api python examples/manager_gym/acceptance.py \
  --stage pilot --output /app/data/mag-acceptance
docker compose exec -T api python examples/manager_gym/acceptance.py \
  --stage catalog --output /app/data/mag-acceptance
```

Run stages in this order. A nonzero exit requires inspecting the saved sample
before continuing. The scripted contract proves dependency order, repeated
human fatigue, pending refinement/reassignment, cancellation, live messaging,
decomposition, E2B artifacts and grading. It is not a MAG quality score.
The cancellation probe stops two running E2B attempts and waits past a delayed spawn to prove the manager cannot reopen work.
The four autonomous pilots precede the remaining catalog. Completed pilots
are reused only under the same source digest, model, seed and limits.

The runner writes `acceptance.json` and, for every terminal sample,
`<sample-id>/records.json`, `context.jsonl.gz` and artifact blobs. It verifies
the exact terminal criterion set, snapshot digest, independently recomputed
utility and E2B sandbox closure. Resume the same command after interruption;
do not relabel a failed sample as a pass. Use a new output folder after code or
configuration changes and retain the failed run's evidence.

For ordinary submissions without the acceptance harness:

```bash
docker compose exec -T api python examples/manager_gym/submit.py \
  --scenario legal_litigation_ediscovery --seed 0 --max-decisions 50
docker compose exec -T api python examples/manager_gym/submit.py \
  --scenario icaap --manager-mode random
docker compose exec -T api python examples/manager_gym/submit.py \
  --scenario marketing_campaign --manager-mode assign_all
```

Use `--all` for all 20 scenario records. `cot` is the default; `random` is
RandomV2 (random action class followed by a model call), and `assign_all` makes
one model-generated mapping, fills gaps with the source fallback, admits
leaves in dependency order, then no-ops. Each uses the same native execution
path. The default action union remains the 13 source actions; bulk assignment
is specific to that baseline.

Default model for **every role and judge**:

```text
openai-compatible:https://api.training.hcompany.ai/v1/models/qwen3-8-27b-28#qwen3-8-27b-28
```

Only explicit internal training gateway targets are accepted by this profile.
There is no OpenAI/OpenRouter/search fallback. Capture the serving image,
weight location/revision if available and deployment configuration separately:
a mutable endpoint name does not identify immutable model weights.

## Interpretation and limits

`mag-native-v1` uses Ergon scheduling and normal completion visibility. Manager
decision indices drive roster/preference changes and stakeholder replies;
simulated labor hours do not delay native execution. Only authored task
dependencies constrain work; actor capacity remains informational. A human
derives fatigue from the completed PostgreSQL attempts visible at invocation
start, so concurrent invocations may capture the same history. Running work cannot be
reassigned; unclaimed work can. No MAG scheduler is embedded.

Model prompts retain source resource previews (300 characters for manager/judge, 200 for AI/human workers) and bounded manager message/action briefs. Native records, callable evaluation inputs and frozen artifacts retain full contents.

The default 50 decisions cover indices 0–49. Seven scenarios contain later
events, so this is an integration profile, not a complete timeline experiment
or evidence of statistical equivalence to upstream. Increase `max_decisions`
in a separately named experiment when studying those events.

The configured E2B account permits a maximum sandbox lifetime of 3,600 seconds.
The manager has a 2,400-second decision budget and a shared 600-second drain
budget; final evaluation also needs time before sandbox expiry. A provider,
deadline or grading failure makes the MAG evaluation incomplete with a null
score. Cancelled prerequisites are valid policy outcomes. Serial grading can
exhaust the remaining lifetime on slow deployments; the acceptance result must
expose that failure rather than silently reduce rubric coverage.

Inference uses at most 32,768 output tokens and a 2,048-token thinking budget, 300 seconds per request,
12 requests per structured operation, two validation retries and a 600-second
outer operation limit. Temperature is 0 for policy/AI/estimator/judge, 0.7 for
human work and 1 for decomposition. Native attempts, successful model usage and
transcripts are retained. Typed workflow checkpoints are ordinary native resource
artifacts under `.checkpoints/`; Inngest records small verified references. Keep
those artifacts with the database and blob volume during restarts and export
them before VM deletion. They are runtime evidence, not task output reports. A provider exception before its checkpoint can lose
that failed call's transcript/usage; zero recorded usage is not proof of zero
requests. Existing task retries are recorded separately.

The thinking cap was verified against the standing deployment after an
exploratory worker exhausted its full output budget. It is a per-request
sampling setting, as documented by [vLLM](https://docs.vllm.ai/en/v0.22.0/features/reasoning_outputs/#thinking-budget-control),
and does not modify the shared deployment. The complete profile is saved in
sample source metadata and the preflight receipt.

To grade an exported snapshot again, run `reevaluate.py --snapshot <path>
--source-sample-id <uuid>` inside the API container. It submits a separate native
sample linked to the original ID and snapshot hash. It rejects JSON that the
current schema would rewrite; use the matching benchmark revision for older
snapshots. Re-evaluation makes fresh judge calls and retains the new model/profile.

Standing internal model capacity avoids a new external inference bill. The VM,
storage and E2B still consume resources; actual monetary charges are unknown
unless checked against account billing. Simulated wage/token costs are
benchmark metrics, not cloud billing.

## Export and cleanup

Before deleting the VM, export the acceptance folder, native database and blob
store. The latter contains the files referenced by persisted resource rows:

```bash
docker compose exec -T postgres pg_dump -U ergon -Fc ergon > data/mag-postgres.dump
tar czf data/mag-blobs.tgz -C /tmp ergon-blob
```

Copy `data/mag-acceptance`, the dump and blob archive to durable storage you
control; verify their hashes and record the destination. Private model traces
can contain scenario work products and belong with run evidence, not a public
PR. Publish a curated receipt with sample IDs, checks, counts and provenance.
Confirm all owned sample sandboxes are closed, run `ergon stop`, then remove
only this VM and its dedicated security group/key. Leave standing model
deployments untouched.
