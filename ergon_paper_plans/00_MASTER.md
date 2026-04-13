# Ergon Paper: Master Plan

**Working title:** *Continuous-Time Event-Driven Substrates for Agentic RL: Beyond the Discrete-Step Abstraction*

**Status:** Pre-submission planning  
**Target venue (primary):** NeurIPS 2026 Workshop — *Scaling Environments for Agents* (deadline ~Aug/Sep 2026)  
**Target venue (backup):** NeurIPS 2026 Workshop — *ML for Systems* or *Foundation Models for Decision Making*  
**Full paper target:** MLSys 2027 (~Oct 2026 deadline) or NeurIPS 2027 Datasets & Benchmarks  

---

## 1. Thesis

Current agentic RL infrastructure forces agent trajectories into the discrete-step `s → a → r → s'` abstraction inherited from Atari/MuJoCo, even though real agentic workloads are natively asynchronous and continuous-time. This abstraction erases wall-clock duration information that is **load-bearing for the optimal policy**: an agent that can't distinguish a 30-second API response from a 6-hour one can't learn when to poll, when to parallelise, or when to abandon — behaviours that define competent real-world agents.

**Core claim:** The discrete-step training abstraction creates a measurable *training-deployment gap* for agentic RL. Policies trained under discrete-step environments degrade when deployed into continuous-time real-world conditions, because their training distribution didn't match deployment.

**Infrastructure claim:** Ergon provides a continuous-time event-driven trajectory substrate that eliminates this gap by natively capturing wall-clock temporal structure, enabling an action space that includes temporal primitives (async dispatch, poll, wait, spawn sub-agents), and supporting fault-tolerant durable execution.

## 2. Contribution Statement (Draft Abstract Seed)

> We identify a previously-unrecognised source of sim-to-real gap in agentic RL: the discrete-step training abstraction erases wall-clock duration information that is necessary for learning duration-dependent optimal policies. We present Ergon, a continuous-time event-driven trajectory substrate for agentic RL that (a) exposes an action space including temporal primitives — async dispatch, poll, wait, spawn — that discrete-step environments structurally cannot represent, (b) natively captures wall-clock temporal structure through to the training loop for credit assignment, (c) subsumes standard synchronous discrete-step RL as a degenerate case under maximal batching, and (d) supports durable fault-tolerant execution via event-sourced state. Using Inngest-backed durable execution with Postgres-persisted event logs, we demonstrate on two domains — deep research (single-agent) and formal theorem proving with sub-agent coordination (multi-agent) — that policies trained under discrete-step abstractions suffer measurable degradation when deployed in continuous-time environments, and that Ergon-trained policies close this gap.

## 3. Key Experimental Design: The Batching Window Sweep

The critical experimental knob: Inngest batching windows allow continuous interpolation from native continuous-time (microsecond events) to fully discrete (single global step). Sweeping this parameter produces a **degradation curve** that:

- Quantifies exactly how much information the discrete abstraction destroys at each granularity
- Identifies the temporal resolution threshold at which specific tasks "break"
- Provides a parametric rather than binary comparison (much harder for reviewers to dismiss)
- Reveals that different workloads have different sensitivity to temporal granularity

**Headline metric:** Cost per completed task (wall-clock, tokens, API calls) under matched compute budgets, with tail percentiles (P95, P99).

**Deployment gap framing:** Train at each batching granularity, deploy in native continuous-time environment, measure performance degradation. The discrete-trained policy looks fine in its own gym but breaks in production.

## 4. Demonstrations

### 4.1 Deep Research — Single-Agent Headline

- Real workload frontier-lab readers immediately recognise
- Natural async structure: parallel search dispatch, variable latencies, polling for results
- Duration-dependent optimal policy: adaptive timeout, opportunistic parallelism, interleaved work during waits
- Batching sweep shows clear degradation as temporal resolution coarsens
- **Metrics:** cost per task (headline), action overlap ratio, polling efficiency, wasted dispatches, P95 tail behaviour

### 4.2 MiniF2F with Sub-Agent Coordination — Multi-Agent

- Parent agent spawns sub-provers for parallel branch exploration
- Coordination action space: spawn, abandon, share lemma, redistribute budget, wait
- Continuous-time advantage: parent learns adaptive branch management based on observed latencies
- Structurally different from deep research (formal mathematics vs information retrieval) — demonstrates substrate generality
- **Go/no-go:** Build prototype by mid-May; if continuous-time advantage doesn't materialise empirically, fall back to deep research only

### 4.3 GDPVal — Breadth and Principled Scope

- Small subset (5-10 tasks) spanning async-sensitive to non-async tasks
- Role: show gap appears specifically where continuous-time structure exists, disappears where it doesn't
- Preempts "is this just deep research?" objection
- **Not** full-suite evaluation; selective with explicit category labels

## 5. Supporting Experiments

| Experiment | Type | Purpose |
|---|---|---|
| Projection loss analysis | Analytical | How many distinct CT trajectories collapse to the same discrete trajectory at each window size? Establishes information loss is structural. |
| Fault injection | Systems | Durability claims: worker crashes, preemption, judge timeouts, recovery latency distributions |
| Framework agnosticism | Demo | Same trajectories consumed by TRL + one other framework (CleanRL or JAX-based) |
| Failure mode taxonomy | Qual+Quant | Categorise and count specific discrete-trained pathologies: fixed-interval polling, false serialisation, premature commitment, retry mistiming |

## 6. Paper Structure (Workshop, ~8 pages)

1. **Introduction** — The training-deployment gap caused by discrete-step abstraction. Inbox/polling motivating example. Connects to sim-to-real tradition.
2. **Background** — SMDPs, event-driven MDPs, Dec-POMDPs. Position against existing MARL infra and discrete-step frameworks.
3. **Ergon: System Design** — Event-driven coordination topology, event log as trajectory substrate, durability model, action space with temporal primitives. Design doc becomes this section.
4. **Experiments: Deep Research** — Full batching sweep, cost metrics, degradation curves, failure mode examples.
5. **Experiments: MiniF2F MAS** — Sub-agent coordination, demonstration of substrate generality. (Compact section; methodology detail in appendix.)
6. **Experiments: GDPVal Breadth** — Small table showing gap by task category.
7. **Discussion** — When does CT matter? (Where degradation curves are steep.) Where doesn't it? (MiniF2F without MAS framing; synchronous reasoning tasks.) Limitations. Scope of durability claims.
8. **Related Work** — Async MARL, SMDP theory, vLLM/verl/SkyRL/ART positioning, event sourcing in distributed systems.

## 7. Timeline

| When | What | Deliverable |
|---|---|---|
| **Apr 14 – Apr 28** | Design doc: formalise event log semantics, POSG/SMDP mapping, durability contract | `01_THEORY.md` filled out; shareable doc |
| **Apr 28 – May 12** | Literature survey: async MARL, SMDP, event-sourcing for RL, sim-to-real in agentic settings | Related work section draft; novelty confirmed or framing adjusted |
| **May 1 – May 15** | MiniF2F MAS prototype: sub-agent spawning, coordination action space, preliminary experiment | Go/no-go on second demonstration |
| **May 15 – Jun 1** | Deep research async action primitives: dispatch_async, poll, wait_for_any in Ergon | Feature complete for headline experiment |
| **Jun 1 – Jun 7** | Blog post draft (tease paper, not replacement for it) | Published on DeepFlow blog |
| **Jun 8** | H Company start date — bandwidth drops ~70-80% | |
| **Jun – Aug** | Passive data collection; NTU integration; accumulate logs from real runs | Measurement database grows |
| **Late May / Jun** | NeurIPS 2026 workshop list announced — confirm target workshop | Workshop selected |
| **Aug – Sep** | Write workshop paper (3-4 weekends of focused work if design doc + lit survey are done) | Submission |
| **Dec 2026** | NeurIPS 2026 (if accepted) — present, network, collect feedback | In-person presence |
| **Oct 2026** | (If targeting MLSys 2027) Full paper submission with extended evaluation | MLSys submission |

## 8. Authorship Plan

| Author | Role | Contribution |
|---|---|---|
| Charlie Masters | First author | System design, implementation, experiments, writing |
| Ziyuan Liu | Middle author | NTU integration, external workload validation |
| [DeepFlow contributors] | Middle author(s) | Ergon engineering contributions (if material) |
| Stefano Albrecht | Senior/last author | MARL formalism, theoretical positioning, MA-Gym research arc |

**Action items:**
- [ ] Discuss co-authorship with Stefano — confirm author order, contribution expectations
- [ ] Confirm Ziyuan's involvement and timeline for NTU integration
- [ ] Clarify H Company IP situation in writing before Jun 8

## 9. Key Risks

| Risk | Mitigation |
|---|---|
| MiniF2F MAS doesn't show CT advantage | Go/no-go by mid-May; fall back to deep research + GDPVal |
| Workshop rejected | Resubmit to ICLR 2027 workshop; roll into MLSys 2027 full paper regardless |
| H bandwidth insufficient for paper writing | Design doc + lit survey done pre-H; paper is a writing exercise from existing materials |
| Inngest batching knob doesn't semantically discretise trajectories | Verify knob semantics in first week of experiments; budget 2 days for this |
| Prior work covers the infrastructure gap | Literature survey in April surfaces this early; adjust framing if needed |
| H IP conflict | Get written confirmation from Faustine/manager before Jun 8 |

## 10. Document Map

| Document | Purpose |
|---|---|
| `00_MASTER.md` (this file) | Overall plan, timeline, authorship, risks |
| [`01_THEORY.md`](./01_THEORY.md) | Formal framework: SMDPs, event-driven MDPs, POSG mapping, durability contract, contribution positioning |
| [`02_EXPERIMENTS.md`](./02_EXPERIMENTS.md) | Detailed experimental protocol: tasks, metrics, baselines, statistical methodology |
| [`03_FEATURE_ROADMAP.md`](./03_FEATURE_ROADMAP.md) | Engineering features needed for paper experiments, with priority and timeline |
| [`features/`](./features/) | Per-feature subfolders with RFCs and engineering plans |
