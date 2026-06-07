# Training Examples

Concrete trainer scripts live here because each script chooses an RL
formalism. Shared HTTP/config/device helpers stay in `ergon_infra`.

`trl_single_agent_stochastic.py` is the first baseline: the parent actor is
trained as a single agent, child spawns are treated as stochastic environment
transitions, and reward is the sample-level normalized score.
