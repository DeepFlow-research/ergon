/**
 * Canonical smoke Playwright spec for the researchrubrics leg.
 *
 * One canonical sad-path run. All assertions live in the shared factory.
 */

import { defineSmokeSpec } from "./_shared/smoke";

defineSmokeSpec({ env: "researchrubrics" });
