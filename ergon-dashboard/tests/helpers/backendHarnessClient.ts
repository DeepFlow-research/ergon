/**
 * Backend test-harness client (distinct from the dashboard's
 * /api/__danger__/test-harness/dashboard/* client in ./testHarnessClient.ts).
 *
 * Hits the FastAPI backend at ERGON_API_BASE_URL. Read-only; smoke specs use this to
 * assert against real sample state by polling the backend directly (not
 * through the dashboard's Socket.io stream).
 *
 * Kept narrow — only the DTOs smoke specs need.  Additive-only.
 */

export interface BackendSampleState {
  sample_id: string;
  status: "completed" | "failed" | "cancelled" | "in_progress" | string;
  graph_nodes: {
    id: string;
    task_slug: string;
    level: number;
    status: string;
    parent_task_id: string | null;
    parent_task_slug: string | null;
  }[];
  events: {
    table: string;
    event_type: string;
    target_id: string | null;
    payload: Record<string, unknown>;
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
  event_count: number;
  resource_count: number;
  thread_count: number;
  context_event_count: number;
}

export interface BackendExperimentSample {
  sample_id: string;
  status: string;
}

export class BackendHarnessClient {
  constructor(private readonly baseUrl: string) {}

  async getSampleState(sampleId: string): Promise<BackendSampleState> {
    const r = await fetch(
      `${this.baseUrl}/api/__danger__/test-harness/read/samples/${sampleId}/state`,
    );
    if (!r.ok) {
      throw new Error(`harness ${r.status}: ${await r.text()}`);
    }
    return r.json() as Promise<BackendSampleState>;
  }

  async getExperimentSamples(experiment: string): Promise<BackendExperimentSample[]> {
    const r = await fetch(
      `${this.baseUrl}/api/__danger__/test-harness/read/experiment/${encodeURIComponent(experiment)}/samples`,
    );
    if (!r.ok) {
      throw new Error(`harness ${r.status}: ${await r.text()}`);
    }
    return r.json() as Promise<BackendExperimentSample[]>;
  }
}
