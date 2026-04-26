/**
 * Backend test-harness client (distinct from the dashboard's
 * /api/test/dashboard/* client in ./testHarnessClient.ts).
 *
 * Hits the FastAPI backend at ERGON_API_BASE_URL, gated by
 * X-Test-Secret: TEST_HARNESS_SECRET. Read-only; smoke specs use this to
 * assert against real run state by polling the backend directly (not
 * through the dashboard's Socket.io stream).
 *
 * Kept narrow — only the DTOs smoke specs need.  Additive-only.
 */

export interface BackendRunState {
  run_id: string;
  status: "completed" | "failed" | "cancelled" | "in_progress" | string;
  graph_nodes: {
    id: string;
    task_slug: string;
    level: number;
    status: string;
    parent_node_id: string | null;
    parent_task_slug: string | null;
  }[];
  mutations: {
    sequence: number;
    mutation_type: string;
    target_task_slug: string | null;
  }[];
  evaluations: {
    task_id: string;
    task_slug: string | null;
    score: number;
    reason: string;
  }[];
  executions: {
    task_slug: string | null;
    status: string;
    error: string | null;
  }[];
  execution_count: number;
  mutation_count: number;
  resource_count: number;
  thread_count: number;
  context_event_count: number;
}

export interface BackendCohortRun {
  run_id: string;
  status: string;
}

export class BackendHarnessClient {
  constructor(
    private readonly baseUrl: string,
    private readonly secret: string,
  ) {}

  private headers(): HeadersInit {
    return { "X-Test-Secret": this.secret };
  }

  async getRunState(runId: string): Promise<BackendRunState> {
    const r = await fetch(
      `${this.baseUrl}/api/test/read/run/${runId}/state`,
      { headers: this.headers() },
    );
    if (!r.ok) {
      throw new Error(`harness ${r.status}: ${await r.text()}`);
    }
    return r.json() as Promise<BackendRunState>;
  }

  async getCohortRuns(cohortKey: string): Promise<BackendCohortRun[]> {
    const r = await fetch(
      `${this.baseUrl}/api/test/read/cohort/${encodeURIComponent(cohortKey)}/runs`,
      { headers: this.headers() },
    );
    if (!r.ok) {
      throw new Error(`harness ${r.status}: ${await r.text()}`);
    }
    return r.json() as Promise<BackendCohortRun[]>;
  }

  async getCohortId(cohortKey: string): Promise<string> {
    const r = await fetch(
      `${this.baseUrl}/api/test/read/cohort/${encodeURIComponent(cohortKey)}/id`,
      { headers: this.headers() },
    );
    if (!r.ok) {
      throw new Error(`harness ${r.status}: ${await r.text()}`);
    }
    const body = (await r.json()) as { cohort_id: string };
    return body.cohort_id;
  }
}
