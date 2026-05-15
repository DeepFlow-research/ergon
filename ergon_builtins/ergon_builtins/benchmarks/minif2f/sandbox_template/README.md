# MiniF2F Lean Verification Sandbox

E2B sandbox template for formal proof verification with Lean 4.

## What's in the image

- **elan** (Lean version manager) installed to `/root/.elan`
- **Lean 4 toolchain** `leanprover/lean4:v4.29.0`
- **mathlib4** `v4.29.0` cloned to `/tools/mathlib_project`
- **Pre-cached oleans** via `lake exe cache get` (no source builds at task time)
- `/tools/mathlib_project/src/` pre-created for writing `verify.lean`

## Build time

- **Cached (normal):** ~3-5 minutes. The `lake exe cache get` step downloads
  pre-built `.olean` files from the mathlib Azure blob cache.
- **Uncached fallback:** Hours. If the cache is missing for the pinned tag,
  mathlib compiles from source. This should never happen for a tagged release.
  If it does, check that `v4.29.0` still has published cache artifacts.

## Building

```bash
export E2B_API_KEY=<your-runtime-key>
ergon benchmark setup minif2f           # builds + pushes to E2B
ergon benchmark setup minif2f --force   # rebuild even if registered
```

Internally this uses the **E2B Python SDK** (`e2b.Template.build()`), not the
`e2b` CLI — so only `E2B_API_KEY` is needed, **not** `E2B_ACCESS_TOKEN`.  The
template is built remotely by E2B's build service from the Dockerfile in this
directory; after a successful build the template_id is persisted to
`~/.ergon/sandbox_templates.json`.

## Verifying the template

```bash
python -c "
import asyncio, os
from e2b_code_interpreter import AsyncSandbox
async def check():
    sbx = await AsyncSandbox.create(template='<template_id>', timeout=300)
    try:
        r = await sbx.commands.run('bash -c \"lean --version\"')
        print(r.stdout)
    finally:
        await sbx.kill()
asyncio.run(check())
"
```

## Versioning

Bump the template name to `-v2` (or higher) on **any** change to:
- Lean toolchain version
- mathlib4 revision
- Dockerfile logic

Do not mutate `-v1` after it has been published. Users' persisted
`template_id` references the immutable image.
