# Theory Document

**Status:** Skeleton — to be fleshed out over the coming weeks  
**Purpose:** Formalise the theoretical framework underpinning the paper's contribution. This document becomes Section 2 (Background) and Section 3 (System Design) of the workshop paper.

---

## 1. The Problem: Discrete-Step Abstraction as Lossy Projection

### 1.1 Standard Agentic RL Formulation

The standard formulation treats agentic interaction as a discrete-time MDP:

```
(S, A, T, R, γ)
```

where at each integer timestep `t`, the agent observes `s_t ∈ S`, selects `a_t ∈ A`, receives `r_t = R(s_t, a_t)`, transitions to `s_{t+1} ~ T(·|s_t, a_t)`.

**What this erases:** Wall-clock duration of actions. A tool call that takes 30ms and one that takes 6 hours both consume one "step." The policy `π(a|s)` cannot condition on elapsed time because elapsed time is not in the state representation.

### 1.2 The Projection

Define the *discrete projection* operator `Π_W` parameterised by batching window `W`:

```
Π_W : τ_ct → τ_discrete
```

where `τ_ct` is the continuous-time event stream and `τ_discrete` is the discrete-step trajectory obtained by batching events into windows of duration `W`.

**Key property:** `Π_W` is many-to-one. Multiple distinct continuous-time trajectories collapse to the same discrete representation. Information is destroyed.

**Claim to formalise:** The information destroyed by `Π_W` is load-bearing for the optimal policy when the optimal action depends on wall-clock durations. Specifically:

- Let `π*_ct` be the optimal policy under the continuous-time formulation
- Let `π*_W` be the optimal policy under the projection `Π_W`
- The *projection regret* `J(π*_ct) - J(π*_W)` is non-zero and monotonically increasing in `W` for tasks with duration-dependent optimal policies

### 1.3 When Does Duration Matter?

Duration-dependent optimal policies arise when:

1. **Adaptive polling:** Optimal check frequency depends on observed latency distributions (e.g., inbox polling, search result arrival)
2. **Opportunistic parallelism:** Whether to dispatch additional work depends on expected wait time for pending results
3. **Adaptive timeout:** When to abandon a pending operation depends on wall-clock elapsed time relative to historical distributions
4. **Interleaved work:** What to do during idle time depends on how long the idle period is expected to last
5. **Multi-agent coordination:** When to redistribute resources across sub-agents depends on observed progress rates

**Concrete example (paper motivation):** A deep research agent dispatches a web search. Under discrete-step RL, step `t` is "dispatch search" and step `t+1` is "receive result." The agent cannot learn that fast searches (30s) should trigger follow-up immediately while slow searches (300s) should trigger parallel work during the wait, because the step abstraction cannot distinguish these durations.

---

## 2. Formal Framework: Event-Driven Semi-Markov Decision Processes

### 2.1 Connection to SMDPs

The Semi-Markov Decision Process (SMDP) framework (Sutton, Precup, Singh 1999) extends MDPs with variable-duration actions. In an SMDP:

```
(S, A, T, R, F)
```

where `F(τ|s, a)` is the distribution over holding times `τ` — the wall-clock duration before the next decision point.

**Ergon's event log is a natural SMDP trajectory representation.** Each event has a wall-clock timestamp; the inter-event duration is the holding time. The discrete-step MDP is the degenerate case where `F` is a point mass at `τ = 1`.

### 2.2 Event-Indexed Trajectories

Define an *event-indexed trajectory* as:

```
τ = {(e_i, t_i, a_i, s_i, o_i)}_{i=1}^{N}
```

where:
- `e_i` is the event type (agent action, tool result, observation, reward signal)
- `t_i ∈ ℝ⁺` is the wall-clock timestamp (microsecond precision)
- `a_i` is the agent identifier (for multi-agent settings)
- `s_i` is the agent-local state at decision time
- `o_i` is the observation scope (what this agent could see)

**Properties:**
- Events are partially ordered by causal dependencies, not just temporally ordered
- Multiple events can be concurrent (parallel tool dispatches)
- The trajectory has a natural DAG structure reflecting causal and information flow

### 2.3 Temporal Action Space

Standard agentic RL: `A = {tool_1, tool_2, ..., respond}`

Ergon's action space includes *temporal primitives*:

```
A_ct = A_standard ∪ {dispatch_async(tool, args), poll(pending_id), 
                      wait(duration), wait_for_any(pending_set),
                      cancel(pending_id), spawn_subagent(spec)}
```

**Key distinction:** Under `A_standard`, every action is synchronous — the agent blocks until the tool returns. Under `A_ct`, the agent can have multiple in-flight operations and must manage its own time. The policy class under `A_ct` is strictly richer than under `A_standard`.

### 2.4 Reduction to Discrete-Time as Limit Case

**Claim:** Discrete-time step-based RL is recovered from the event-driven formulation as the limit case where:

1. The batching window `W → ∞` (all events collapse to a single step), or equivalently
2. The action space excludes all temporal primitives, reducing `A_ct → A_standard`
3. All agents are synchronised to a global clock (MAS → synchronous rounds)

This gives a clean subsumption relationship: everything existing frameworks can do, Ergon can do. The reverse is not true.

---

## 3. Multi-Agent Extension: POSG Substrate

### 3.1 From Single-Agent to POSG

A Partially Observable Stochastic Game (POSG) extends the SMDP framework to multiple agents:

```
(N, S, {A_i}, {O_i}, T, {R_i}, {Ω_i})
```

where each agent `i` has its own action space `A_i`, observation function `Ω_i`, and reward function `R_i`.

### 3.2 Coordination Topology

Ergon's DAG defines the *coordination topology* — which agents can observe, communicate with, or influence which other agents. This is a structural property of the multi-agent system, not of the execution engine.

```
G = (V, E) where V = {agents}, E = {(i,j) : agent i can observe/influence agent j}
```

The topology is:
- **Dynamic:** Edges can be created at runtime (sub-agent spawning)
- **Observable:** The topology itself is part of the logged state
- **First-class in the event schema:** Not inferred post-hoc from message patterns

### 3.3 Per-Agent Observation Scope

In a POSG, agent `i` observes only `o_i = Ω_i(s)`, not the full state. For the event log to be a valid POSG trajectory, it must record per-agent observation scope:

**What agent `i` could see at time `t`** is determined by:
- The coordination topology edges incoming to `i` at time `t`
- The events that have propagated along those edges by time `t`
- The agent's own local state history

**TODO:** Verify whether the current Ergon schema captures this. Key questions:
- [ ] Can we reconstruct per-agent `(o_i, a_i, r_i)` sequences from the Postgres state?
- [ ] Is the coordination topology explicit in the schema or implicit in event patterns?
- [ ] Does `RunGraphAnnotation` carry enough information for observation scoping?

### 3.4 Existing Schema Mapping

| POSG concept | Ergon schema element | Status |
|---|---|---|
| Agent identity | `worker_binding_key` on `RunGenerationTurn` | ✅ Exists |
| Agent action | `RunGenerationTurn.raw_response` + tool calls | ✅ Exists |
| Wall-clock timestamp | `RunGenerationTurn.created_at` (microsecond) | ✅ Exists |
| Coordination topology | `RunGraphNode` + `RunGraphEdge` per run | ✅ Structure exists |
| Per-agent observation scope | Partially via `Thread` / `ThreadMessage` | ⚠️ Needs verification |
| Causal ordering | `RunGraphAnnotation` sequence + `RunGraphMutation` sequence | ✅ Append-only WAL |
| Inter-agent communication | `Thread` / `ThreadMessage` with `from_agent_id` / `to_agent_id` | ✅ Exists |
| Per-agent reward | `RewardStrategy.assign()` per `worker_binding_key` | ✅ Exists |
| Topology mutations | `RunGraphMutation` (node/edge add/remove/change) | ✅ Append-only log |

---

## 4. The Training-Deployment Gap

### 4.1 Sim-to-Real Analogy

The discrete-step abstraction is a *simulator* that misrepresents the real environment. Training in it produces policies adapted to the simulator, not to reality. This is precisely the sim-to-real gap, but along the temporal-fidelity axis rather than the physics-fidelity axis.

**Formal statement (to refine):**

Let `E_ct` be the real continuous-time environment and `E_W = Π_W(E_ct)` be its discrete projection at window `W`. A policy `π_W` trained in `E_W` and deployed in `E_ct` incurs a *temporal sim-to-real gap*:

```
Gap(W) = J_{E_ct}(π*_ct) - J_{E_ct}(π_W)
```

where `J_{E_ct}(π)` is the expected return of policy `π` deployed in the real environment.

**Properties to establish empirically:**
- `Gap(W)` is monotonically non-decreasing in `W` (more batching → worse deployment)
- `Gap(W) ≈ 0` for tasks without duration-dependent optimal policies
- `Gap(W) >> 0` for tasks with genuine temporal structure (deep research, coordinated proof search)

### 4.2 Why Observing Time Isn't Sufficient

A sharp reviewer will counter: "just add wall-clock time as an observation feature." Response:

- **Observing time ≠ learning from time.** Credit assignment operates at step granularity. The gradient update attributes reward to step boundaries, not to continuous-time intervals.
- The policy might see `Δt = 300s` in observation but the training signal can't distinguish "this reward was because you waited the right amount" from "this reward was because the tool result happened to be good."
- Under `A_standard`, the agent can't *act* on temporal information even if it observes it — the action space doesn't include "wait" or "dispatch async."

### 4.3 Information-Theoretic Characterisation

**TODO:** Formalise the information loss. Possible approaches:

- Mutual information between trajectory and optimal action under CT vs discrete
- Conditional entropy of next action given elapsed time (measures whether the policy uses temporal information)
- Channel capacity of the discrete projection as a function of `W`

---

## 5. Durability and Event Sourcing

### 5.1 Event Sourcing as Trajectory Representation

Ergon's persistence model is event-sourced: the append-only `RunGraphAnnotation` and `RunGraphMutation` tables constitute a write-ahead log from which the full system state can be reconstructed at any point in the execution history. This is not incidental — it's the same property that makes the event log a valid trajectory for training.

**Key invariant:** The event log is the single source of truth for both execution recovery and trajectory extraction. The same data structure that enables fault tolerance enables RL training.

### 5.2 Recovery Semantics

**TODO:** Specify precisely:
- What is persisted at what granularity (per-yield `GenerationTurn` → PG commit)
- What the recovery semantics are (which events replay, which are idempotent)
- Under what conditions replay produces an equivalent trajectory
- How in-flight judge calls are handled during recovery

### 5.3 Durability as Experimental Enabler

Fault tolerance isn't just a systems feature — it's what makes the experiments tractable:
- Long-horizon rollouts (hours) without manual intervention
- Preemption recovery on spot instances (SkyPilot)
- Judge timeout handling without losing partial results
- The "72-hour multi-agent RL job with 4 preemptions and zero human intervention" sentence

---

## 6. Literature to Survey

### 6.1 Formal Frameworks
- [ ] Sutton, Precup, Singh (1999) — Between MDPs and semi-MDPs: Options framework
- [ ] Bradtke & Duff (1994) — RL methods for continuous-time MDPs
- [ ] Event-driven MDP literature (control theory side)
- [ ] Dec-POMDP infrastructure: Omidshafiei et al.

### 6.2 Async MARL
- [ ] Foerster group work on async multi-agent learning
- [ ] Continuous-time MARL from control theory
- [ ] Event-driven MARL recent papers

### 6.3 Systems and Infrastructure
- [ ] vLLM (Kwon et al.) — systems-as-contribution precedent
- [ ] verl, SkyRL, ART — RL training infrastructure landscape
- [ ] Ray, Temporal, Inngest — execution engine comparisons
- [ ] Event sourcing / CQRS patterns applied to ML

### 6.4 Sim-to-Real and Distribution Shift
- [ ] Domain randomisation literature (robotics)
- [ ] Distribution shift in agentic RL specifically
- [ ] Robust RL under environment mismatch

### 6.5 Agent Benchmarks and Environments
- [ ] GDPVal, SWE-Bench, WebArena — existing agentic benchmarks
- [ ] MiniF2F — formal mathematics
- [ ] MA-Gym (Masters & Albrecht, DAI 2025) — predecessor work

---

## 7. Open Questions (To Resolve via This Document)

1. **Is the SMDP framing sufficient, or do we need the full event-driven MDP?** SMDPs assume the next state depends only on the current state and action, not on the holding time. If the environment changes during the wait (other agents act, search results arrive), we may need a richer formalism.

2. **What's the right formal object for the event log?** Candidates: timed automaton, event structure (concurrency theory), or just "SMDP trajectory with concurrent actions."

3. **How does partial observability interact with continuous time in the MAS case?** Standard Dec-POMDP assumes synchronous rounds. We need to specify what "observation at time t" means when different agents are at different points in their execution.

4. **Is the batching window `W` the right experimental knob, or is there a richer parameterisation?** The window batches events uniformly in time. Real discrete-step abstractions batch at action boundaries, which is non-uniform. Does this distinction matter?

5. **Can we prove (even informally) that the projection regret is monotone in `W`?** If not, the experimental sweep might show non-monotonic behaviour which needs explanation.

6. **Where exactly does prior work stop and our contribution begin?** The SMDP framework exists. Event sourcing exists. Agent environments exist. The contribution must be crisply positioned at the intersection — "we're the first to build infrastructure that respects the SMDP formalism for real agentic workloads" — and the lit survey needs to confirm this.
