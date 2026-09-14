---
status: open
opened: 2026-09-14
fixed_pr: null
priority: P2
invariant_violated: docs/architecture/05_dashboard.md
related_rfc: docs/rfcs/active/2026-09-07-manager-gym-port/
---

# Linux dashboard development startup cannot rewrite mounted source

The rebuilt v14 dashboard container started `tsx watch server.ts` through the
normal development Compose configuration. Next.js then failed with
`EACCES: permission denied, open '/app/next-env.d.ts'`. Its unprivileged user
could not rewrite the bind-mounted source file. The API was healthy, but the
dashboard port and Socket connection were unavailable. No fresh model work had
been launched.

The original runbook selected its override with a shell-only `COMPOSE_FILE`
export. A later SSH session recreated containers using the default development
commands. The runbook now persists `COMPOSE_FILE` in the ignored deployment
`.env`; the effective configuration is checked before recreation.

The Linux acceptance overlay now runs the existing built production server
with `pnpm start` and `NODE_ENV=production`. Production startup consumes the
compiled bundle without rewriting development TypeScript declarations. The
container remains unprivileged; source permissions and the normal local
development configuration are unchanged.

The exact source execution digest remains v14. Deployment configuration is
retained separately. Verify HTTP health and the real Inngest-to-Socket large
evaluation proof on Linux before starting native acceptance.
