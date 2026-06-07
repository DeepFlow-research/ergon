import type { APIRequestContext } from "@playwright/test";

export interface TestGraphNodeDto {
  id: string;
  task_slug: string;
  level: number;
  status: string;
  parent_task_id: string | null;
  parent_task_slug: string | null;
}

export interface TestEvaluationDto {
  task_id: string;
  task_slug: string | null;
  score: number;
  reason: string;
}

export interface TestSampleRuntimeEventDto {
  sequence: number;
  event_type: string;
  target_task_slug: string | null;
}

export interface TestSampleStateDto {
  sample_id: string;
  status: string;
  graph_nodes: TestGraphNodeDto[];
  events: TestSampleRuntimeEventDto[];
  evaluations: TestEvaluationDto[];
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

export class BackendHarnessClient {
  constructor(
    private readonly request: APIRequestContext,
    private readonly baseUrl: string,
  ) {}

  async getSampleState(sampleId: string): Promise<TestSampleStateDto> {
    const response = await this.request.get(
      `${this.baseUrl}/api/__danger__/test-harness/read/samples/${sampleId}/state`,
    );
    if (!response.ok()) {
      throw new Error(
        `BackendHarnessClient.getSampleState failed: ${response.status()} ${await response.text()}`,
      );
    }
    return (await response.json()) as TestSampleStateDto;
  }
}
