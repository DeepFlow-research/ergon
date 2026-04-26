/**
 * Canonical smoke Playwright spec for the swebench-verified leg.
 *
 * One canonical sad-path run. All assertions live in the shared factory.
 */

import { defineSmokeSpec } from "./_shared/smoke";

defineSmokeSpec({ env: "swebench-verified" });
