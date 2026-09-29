# Manager Gym live acceptance

These drivers check a deployed Ergon stack end to end with Manager Gym: real E2B sandboxes, the
real model target and Ergon's own scheduling and grading. They are scripts, not pytest tests;
their offline logic is covered by
`ergon_builtins/tests/unit/builtins/benchmarks/manager_gym/test_acceptance.py`.

Run them inside the API container, where `tests/` is mounted:

```bash
MODEL=openai-compatible:http://vllm:8000#Qwen/Qwen3-32B
OUT=/app/data/mag-acceptance

docker compose exec -T api python tests/real_llm/manager_gym/step_error.py --output $OUT
docker compose exec -T api python tests/real_llm/manager_gym/cancellation.py --output $OUT
docker compose exec -T api python tests/real_llm/manager_gym/acceptance.py \
  --stage contract --model $MODEL --output $OUT
docker compose exec -T api python tests/real_llm/manager_gym/acceptance.py \
  --stage pilot --model $MODEL --output $OUT --timeout-seconds 14400
docker compose exec -T api python tests/real_llm/manager_gym/acceptance.py \
  --stage catalog --model $MODEL --output $OUT --timeout-seconds 36000
```

- `step_error.py` checks that a scripted failure keeps its original exception type, message and
  traceback through Inngest replay, and that its sandbox is closed. It makes no model calls.
- `cancellation.py` cancels a sample with two running attempts and a delayed spawn, and checks
  that nothing reopens.
- `acceptance.py --stage contract` runs a scripted episode covering dependency order, repeated
  human fatigue, refinement and reassignment, cancellation, messaging, decomposition, E2B
  artifacts and grading. It is a runtime contract, not a MAG score.
- `--stage pilot` runs four scenarios, and `--stage catalog` all twenty, with the real model.

Run the stages in that order. `acceptance.json` in the output folder is a ledger: rerunning the
same command resumes it, and a folder recorded under a different code digest, model or limits
is refused. After a failed sample, no new samples are admitted; those already running finish
and are exported. For every finished sample the driver writes `records.json`, a compressed
context log and the artifact blobs, and checks the terminal criterion set, the snapshot digest,
an independently recomputed utility and sandbox closure.

`compose.acceptance.yml` is an optional overlay that runs the API without reload and the
dashboard from its production build, which avoids writing into a source bind mount owned by
another user:

```bash
docker compose -f docker-compose.yml -f tests/real_llm/manager_gym/compose.acceptance.yml up -d
```
