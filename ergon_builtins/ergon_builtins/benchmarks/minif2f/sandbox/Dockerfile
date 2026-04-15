# E2B sandbox image: Lean 4 + mathlib4 (pre-cached oleans)
# Template: ergon-minif2f-v1
#
# Pinned versions (do not change without bumping template name to -v2):
#   Lean toolchain: leanprover/lean4:v4.29.0
#   mathlib4 rev:   v4.29.0
#
# Expected build time: ~3-5 min (cached oleans); hours if cache miss (do not allow).

FROM ubuntu:22.04

ARG LEAN_TOOLCHAIN=leanprover/lean4:v4.29.0
ARG MATHLIB_REV=v4.29.0

# --- System dependencies ---
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Install elan (Lean version manager) system-wide ---
# E2B's base image runs sandboxes as a non-root `user` account (uid 1000), so
# elan must live somewhere world-readable, not in /root/.elan.  Install to
# /opt/elan and expose its bin dir on the global PATH.
ENV ELAN_HOME=/opt/elan
ENV PATH="/opt/elan/bin:${PATH}"

RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf \
    | sh -s -- -y --default-toolchain none --no-modify-path

# --- Install and pin Lean toolchain ---
RUN elan toolchain install ${LEAN_TOOLCHAIN} \
    && elan default ${LEAN_TOOLCHAIN}

# --- Clone mathlib4 at pinned tag ---
RUN git clone --depth 1 --branch ${MATHLIB_REV} \
    https://github.com/leanprover-community/mathlib4 /tools/mathlib_project

# --- Download pre-built oleans (the expensive step) ---
# This MUST hit the Azure blob cache for the pinned tag.  If it falls back to
# source compilation the build will take hours and should be considered broken.
WORKDIR /tools/mathlib_project
RUN lake exe cache get

# --- Pre-create src/ directory for verify.lean writes at task time ---
RUN mkdir -p /tools/mathlib_project/src

# --- Make everything the sandbox user will touch readable/writable ---
# E2B's base image runs sandboxes as `user` (uid 1000), but the build above
# ran as root, so every file under /opt/elan and /tools/mathlib_project is
# root-owned.  Two consequences if left alone:
#   1. `lake env` can't write to .lake/ at task time.
#   2. `git` refuses to read .git dirs inside .lake/packages/* with a
#      "dubious ownership" error, which makes lake think the package URL
#      changed and triggers a (broken) re-clone at runtime.
# Fix both by chowning the mathlib tree to uid 1000 and loosening elan perms.
RUN chmod -R a+rX /opt/elan \
    && chown -R 1000:1000 /tools/mathlib_project \
    && git config --system --add safe.directory '*'

# --- Expose Lean tooling on the default runtime PATH ---
# E2B's sandbox runtime does NOT inherit Dockerfile ENV PATH across process
# boundaries; the default sandbox PATH is /usr/local/sbin:/usr/local/bin:...
# Symlink every elan-managed binary into /usr/local/bin so commands like
# `lake env lean` resolve without any PATH rigging from the caller.
# Also drop an /etc/profile.d snippet for login shells + ELAN_HOME export.
RUN for bin in /opt/elan/bin/*; do \
        ln -sf "$bin" "/usr/local/bin/$(basename $bin)"; \
    done \
    && printf 'export ELAN_HOME=/opt/elan\nexport PATH=/opt/elan/bin:$PATH\n' \
        > /etc/profile.d/elan.sh \
    && chmod 0644 /etc/profile.d/elan.sh

# --- Pre-create agent workspace dirs owned by the sandbox user ---
# The E2B sandbox runs as uid 1000 who cannot mkdir at /. Pre-create the
# working dirs the ReAct agent writes into (drafts, final proofs, inputs)
# so the worker does not need sudo at task time.
RUN mkdir -p /workspace/scratchpad /workspace/final_output /inputs /skills \
    && chown -R 1000:1000 /workspace /inputs /skills \
    && chmod -R 0775 /workspace /inputs /skills

# --- Smoke test: fail the build loudly if setup is broken ---
RUN lake env lean --version \
    && /usr/local/bin/lake env lean --version

WORKDIR /workspace
