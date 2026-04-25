import type { APIRequestContext } from "@playwright/test";

export interface TestGraphNodeDto {
  id: string;
  task_slug: string;
  level: number;
  status: string;
  parent_node_id: string | null;
  parent_task_slug: string | null;
}

export interface TestEvaluationDto {
  task_id: string;
  task_slug: string | null;
  score: number;
  reason: string;
}

export interface TestGraphMutationDto {
  sequence: number;
  mutation_type: string;
  target_task_slug: string | null;
}

export interface TestRunStateDto {
  run_id: string;
  status: string;
  graph_nodes: TestGraphNodeDto[];
  mutations: TestGraphMutationDto[];
  evaluations: TestEvaluationDto[];
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

export class BackendHarnessClient {
  constructor(
    private readonly request: APIRequestContext,
    private readonly baseUrl: string,
  ) {}

  async getRunState(runId: string): Promise<TestRunStateDto> {
    const response = await this.request.get(
      `${this.baseUrl}/api/test/read/run/${runId}/state`,
    );
    if (!response.ok()) {
      throw new Error(
        `BackendHarnessClient.getRunState failed: ${response.status()} ${await response.text()}`,
      );
    }
    return (await response.json()) as TestRunStateDto;
  }
}
