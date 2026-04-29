"""RL integration layer.

Provides the bridge between Ergon's Inngest-orchestrated environment
plane and external training frameworks (TRL, veRL).

Core components:

- ``extraction``: per-agent trajectory extraction from RunContextEvent rows
- ``rewards``: reward strategies for per-agent credit assignment
- ``rollout_service``: service client for managed rollout execution
"""
