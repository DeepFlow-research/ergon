import { config } from "@/lib/config";
import {
  parseCohortDetail,
  parseCohortSummary,
  parseCohortSummaryList,
  type CohortDetail,
  type CohortSummary,
  type ExperimentCohortStatusValue,
} from "@/lib/contracts/rest";
import { fetchErgonApi } from "@/lib/serverApi";
import {
  getHarnessCohort,
  listHarnessCohorts,
  updateHarnessCohortStatus,
} from "@/lib/testing/dashboardHarness";

import { backendUnavailable, type ServerDataResult } from "./responses";

export async function loadCohortList(
  includeArchived: string | null,
): Promise<ServerDataResult<CohortSummary[]>> {
  const backendPath =
    includeArchived === null ? "/cohorts" : `/cohorts?include_archived=${includeArchived}`;

  if (config.enableTestHarness) {
    const cohorts = listHarnessCohorts();
    if (cohorts.length > 0) {
      return { ok: true, data: cohorts, status: 200, source: "harness" };
    }
  }

  try {
    const response = await fetchErgonApi(backendPath);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseCohortSummaryList(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable("Ergon API is unavailable while loading cohorts.", error);
  }
}

export async function loadCohortDetail(
  cohortId: string,
): Promise<ServerDataResult<CohortDetail>> {
  if (config.enableTestHarness) {
    const detail = getHarnessCohort(cohortId);
    if (detail !== null) {
      return { ok: true, data: parseCohortDetail(detail), status: 200, source: "harness" };
    }
  }

  try {
    const response = await fetchErgonApi(`/cohorts/${cohortId}`);
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseCohortDetail(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while loading cohort ${cohortId}.`, error);
  }
}

export async function updateCohortStatus(
  cohortId: string,
  status: ExperimentCohortStatusValue,
): Promise<ServerDataResult<CohortSummary>> {
  if (config.enableTestHarness) {
    const updated = updateHarnessCohortStatus(cohortId, status);
    if (updated === null) {
      return {
        ok: false,
        body: { detail: `Cohort ${cohortId} not found` },
        status: 404,
        source: "backend",
      };
    }
    return { ok: true, data: parseCohortSummary(updated), status: 200, source: "harness" };
  }

  try {
    const response = await fetchErgonApi(`/cohorts/${cohortId}`, {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
      },
      body: JSON.stringify({ status }),
    });
    const body = await response.json();
    if (response.ok) {
      return {
        ok: true,
        data: parseCohortSummary(body),
        status: response.status,
        source: "backend",
      };
    }
    return { ok: false, body, status: response.status, source: "backend" };
  } catch (error) {
    return backendUnavailable(`Ergon API is unavailable while updating cohort ${cohortId}.`, error);
  }
}
