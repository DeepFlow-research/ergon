/**
 * Canonical smoke Playwright spec for the swebench-verified leg.
 *
 * 3 happy-path cohort runs.  No sad slot.  All assertions in the
 * shared factory (./._shared/smoke.ts).
 */

import { defineSmokeSpec } from "./_shared/smoke";

defineSmokeSpec({ env: "swebench-verified" });
