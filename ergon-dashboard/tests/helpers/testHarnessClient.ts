import type { APIRequestContext } from "@playwright/test";

export interface TestGraphNodeDto {
  task_slug: string;
  level: number;
  status: string;
  parent_task_slug: string | null;
}

export interface TestEvaluationDto {
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
  resource_count: number;
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
