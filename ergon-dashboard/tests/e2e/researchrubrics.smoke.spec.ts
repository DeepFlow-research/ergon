/**
 * Canonical smoke Playwright spec for the researchrubrics leg.
 *
 * Cohort shape: 2 happy + 1 sad (see docs/superpowers/plans/test-refactor/00-program.md §3.2).
 * All assertions defined in the shared factory.
 */

import { defineSmokeSpec } from "./_shared/smoke";

defineSmokeSpec({ env: "researchrubrics" });
