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

# --- Install elan (Lean version manager) as root ---
# E2B sandboxes run as root by default; install to /root/.elan.
RUN curl https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh -sSf \
    | sh -s -- -y --default-toolchain none

ENV PATH="/root/.elan/bin:${PATH}"

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

# --- Smoke test: fail the build loudly if setup is broken ---
RUN lake env lean --version

WORKDIR /workspace
