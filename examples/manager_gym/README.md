# Manager Agent Gym

Run the 20 scenarios of [Manager Agent Gym](https://github.com/DeepFlow-research/manager_agent_gym)
(MAG) on Ergon. In each episode an LLM manager decomposes a project, assigns work to simulated
AI and human workers, answers a stakeholder whose priorities shift, and is scored by MAG's
rubrics on the finished workflow. Scheduling, messaging, sandboxes and grading are native
Ergon; the design is described in
[`docs/architecture/09_manager_gym.md`](../../docs/architecture/09_manager_gym.md).

## Prerequisites

- The Ergon stack running (`ergon start`, then `ergon doctor`).
- `E2B_API_KEY` set: every task, including the manager, runs in an E2B sandbox.
- Credentials for your model provider, for example `OPENAI_API_KEY`, or
  `ERGON_OPENAI_COMPATIBLE_API_KEY` for a hosted OpenAI-compatible endpoint.

One model target drives the manager, every worker and the LLM judge. Pass it with `--model` or
set `ERGON_MAG_MODEL`. Targets use Ergon's usual syntax, for example `openai:gpt-4o` or
`openai-compatible:http://localhost:8000#Qwen/Qwen3-32B` for a local vLLM server.

## Check the model

`preflight.py` makes one small request per role output schema, checks a tool round trip, and
composes every scenario offline. Run it before spending on a full episode:

```bash
docker compose exec -T api python examples/manager_gym/preflight.py \
  --model openai:gpt-4o --output /app/data/mag-preflight.json
```

## Run

```bash
docker compose exec -T api python examples/manager_gym/submit.py \
  --model openai:gpt-4o --scenario icaap
```

The script prints the experiment name and sample IDs; follow progress in the dashboard. Useful
options:

| Option | Meaning |
|---|---|
| `--scenario NAME` | Scenario to run; repeat it to run several. Default `legal_litigation_ediscovery`. |
| `--all` | Run all 20 scenarios. |
| `--manager-mode` | `cot` (default), or upstream's `random` and `assign_all` baselines. |
| `--max-decisions` | Manager decisions per episode (default 50). |
| `--seed` | Seed for the simulated humans and baselines. |
| `--thinking-token-budget` | Reasoning cap for thinking models served by vLLM. |

`random` chooses a random action type and lets the model fill it in; `assign_all` makes one
model-generated assignment of every task, then waits. All three policies share the same
execution path.

## Scores

Each sample's evaluation reports MAG's utility: rubric scores grouped by stakeholder
preference, normalised, and weighted by the final preference weights. Diagnostic rubrics are
reported but excluded from utility. If grading or infrastructure fails, the evaluation is
incomplete (a null score) rather than zero.

Rubric version 2 (the default) fixes three upstream rubric bugs listed in
[the vendored README](../../ergon_builtins/ergon_builtins/benchmarks/manager_gym/_vendor/mag/README.md);
pass `rubric_version=1` to `MAGRubric` to reproduce upstream scoring.

To grade an exported snapshot again, for example with a different judge, submit it as a new
sample linked to the original:

```bash
docker compose exec -T api python examples/manager_gym/reevaluate.py \
  --model openai:gpt-4o --snapshot manager-gym-snapshot.json --source-sample-id <uuid>
```

## Limits

- Fifty decisions cover timesteps 0–49; seven scenarios schedule later events that then do
  not occur. Raise `--max-decisions` in a separately named experiment to study them.
- An episode must finish within the manager's one-hour sandbox lifetime, including grading.
- Model and sandbox costs are separate from the simulated labour cost the benchmark reports.

## Citation

```bibtex
@inproceedings{manager_agent_gym_2025,
  title     = {Orchestrating Human-AI Teams: The Manager Agent as a Unifying Research Challenge},
  author    = {Masters, Charlie and Vellanki, Advaith and Shangguan, Jiangbo and Kultys, Bart
               and Moore, Alastair and Albrecht, Stefano V.},
  booktitle = {Proceedings of the International Conference on Distributed Artificial
               Intelligence (DAI 2025)},
  year      = {2025},
  url       = {https://arxiv.org/abs/2510.02557}
}
```
