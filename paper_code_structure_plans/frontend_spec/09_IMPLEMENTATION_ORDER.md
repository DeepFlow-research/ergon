# Implementation Order

This document defines the intended red-green order for the frontend.

## Principle

Start with deterministic, high-signal failures that localize the problem clearly.

Do not start with broad live browser probes.

## Order

### 1. Cohort View Spec And Seeded-State Tests

Goal:

- define the top-level experiment operations surface before overfitting the FE to a single-run mental model

Why first:

- the product hierarchy now clearly starts at experiment cohort -> run -> task
- this avoids building a run page that has to be recontextualized later

### 2. Runs List Seeded-State Tests

Goal:

- prove basic fetching and terminal-state rendering

Why first:

- if this fails, the problem is probably very early in FE data flow

### 3. Run Detail Seeded-State Tests

Goal:

- prove run summary and main page structure

### 4. Task Graph Seeded-State Tests

Goal:

- prove graph rendering and topology correctness

### 5. Task Detail Seeded-State Tests

Goal:

- prove task evidence rendering

Focus:

- outputs and artifacts are primary when present
- dynamic fallback works when outputs are absent

### 6. Failure-State Tests

Goal:

- prove failed runs and tasks are debuggable

### 7. Controlled-Event Transition Tests

Goal:

- prove live state updates do not corrupt UI truth

### 8. Raw Events Drawer Tests

Goal:

- prove chronological debugging evidence is available without polluting the main run workflow

### 9. Tiny Live Browser Probes

Goal:

- prove the real stack still wires together

## Red-Green Rules

- write the behavior expectation first
- write the smallest meaningful failing browser test
- make it pass without over-generalizing immediately
- keep tests tied to business-visible state
- use the next failing test to drive the next UI refinement

## Exit Condition

The frontend should be considered stable enough for broader work when:

- seeded-state tests define the expected behavior clearly
- controlled-event tests prove update correctness
- raw events inspection works as a secondary tool
- live probes are small and mostly boring
