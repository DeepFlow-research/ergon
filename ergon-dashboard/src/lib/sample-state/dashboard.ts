import type {
  ExperimentDetailView,
  SampleDetailView,
  SampleEventView,
  SampleGraphView,
  SamplerInvocationView,
  EnvironmentContributionView,
  ExperimentSampleSummaryView,
} from "@/lib/contracts/rest";

export interface ExperimentDashboardState {
  experimentId: string;
  name: string;
  description: string | null;
  environments: EnvironmentContributionView[];
  samples: ExperimentSampleSummaryView[];
  samplerInvocations: SamplerInvocationView[];
  sampleCount: number;
  metadata: Record<string, unknown>;
  createdAt: string;
}

export interface SampleDashboardState {
  sampleId: string;
  experimentId: string;
  environmentId: string;
  environmentName: string;
  sampleKey: string;
  sampleRef: Record<string, unknown>;
  sourceMetadata: Record<string, unknown>;
  status: string;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  events: SampleEventView[];
  graph: SampleGraphView;
}

export function buildExperimentState(payload: ExperimentDetailView): ExperimentDashboardState {
  return {
    experimentId: payload.experimentId,
    name: payload.name,
    description: payload.description ?? null,
    environments: payload.environments,
    samples: payload.samples,
    samplerInvocations: payload.samplerInvocations,
    sampleCount: payload.sampleCount,
    metadata: payload.metadata,
    createdAt: payload.createdAt,
  };
}

export function buildSampleState(payload: {
  detail: SampleDetailView;
  events: SampleEventView[];
  graph: SampleGraphView;
}): SampleDashboardState {
  return {
    sampleId: payload.detail.sampleId,
    experimentId: payload.detail.experimentId,
    environmentId: payload.detail.environmentId,
    environmentName: payload.detail.environmentName,
    sampleKey: payload.detail.sampleKey,
    sampleRef: payload.detail.sampleRef,
    sourceMetadata: payload.detail.sourceMetadata,
    status: payload.detail.status,
    createdAt: payload.detail.createdAt,
    startedAt: payload.detail.startedAt ?? null,
    completedAt: payload.detail.completedAt ?? null,
    events: payload.events,
    graph: payload.graph,
  };
}
