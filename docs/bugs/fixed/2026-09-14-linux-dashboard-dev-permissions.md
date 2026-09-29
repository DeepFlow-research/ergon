---
status: fixed
opened: 2026-09-14
fixed_pr: 134
priority: P2
invariant_violated: docs/architecture/05_dashboard.md
related_rfc: null
---

# Bug: Linux dashboard dev server cannot rewrite bind-mounted source

## Symptom

On a Linux host, the dashboard container's development command (`tsx watch server.ts`) failed
with `EACCES: permission denied, open '/app/next-env.d.ts'`. The API stayed healthy, but the
dashboard port and its Socket.io connection were unavailable.

## Root cause

Next.js rewrites `next-env.d.ts` on development startup. The container's unprivileged user
cannot write the bind-mounted source file when the host checkout belongs to another UID.

## Fix

`tests/real_llm/manager_gym/compose.acceptance.yml` runs the dashboard's built production server
(`pnpm start`, `NODE_ENV=production`), which reads the compiled bundle and writes no source
files. The container stays unprivileged, and the normal local development configuration is
unchanged.

## Verification

With the overlay applied on Linux, the dashboard serves HTTP and delivers large evaluation
updates from Inngest to the browser over Socket.io.
