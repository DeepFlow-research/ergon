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

## Building manually

```bash
cd ergon/ergon_builtins/ergon_builtins/benchmarks/minif2f/sandbox/
e2b template build --dockerfile Dockerfile --name ergon-minif2f-v1 \
    --cmd "/bin/bash" --cpu-count 2 --memory-mb 8192
```

The preferred path is the wrapped CLI command (Phase 3):

```bash
ergon benchmark setup minif2f
```

## Verifying the template

```bash
e2b template list   # should show ergon-minif2f-v1
```

## Versioning

Bump the template name to `-v2` (or higher) on **any** change to:
- Lean toolchain version
- mathlib4 revision
- Dockerfile logic

Do not mutate `-v1` after it has been published. Users' persisted
`template_id` references the immutable image.
