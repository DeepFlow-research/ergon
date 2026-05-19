# Ergon Agent Instructions

`CLAUDE.md` is the canonical repo instruction file. Read it before making
changes, especially the **Agent regression guardrails** section.

For Codex-style agents, the short version is: avoid parallel legacy/new
architectures, avoid placeholder runtime code, keep one source of truth for
persistence state, verify the full authoring-to-runtime path with tests, and
update architecture docs in the same PR.
