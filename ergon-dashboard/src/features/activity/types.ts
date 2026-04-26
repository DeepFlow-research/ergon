import type { RunEventKind } from "@/lib/runEvents";

export type ActivityKind =
  | "execution"
  | "graph"
  | "message"
  | "artifact"
  | "evaluation"
  | "context"
  | "sandbox";

export type ActivityBand =
  | "work"
  | "graph"
  | "tools"
  | "communication"
  | "outputs";

export interface ActivityLineage {
  taskId?: string | null;
  taskExecutionId?: string | null;
  sandboxId?: string | null;
  agentId?: string | null;
  workerBindingKey?: string | null;
  threadId?: string | null;
}

export interface RunActivity {
  id: string;
  kind: ActivityKind;
  band: ActivityBand;
  label: string;
  taskId: string | null;
  sequence: number | null;
  startAt: string;
  endAt: string | null;
  isInstant: boolean;
  actor: string | null;
  sourceKind:
    | RunEventKind
    | "execution.span"
    | "sandbox.span"
    | "sandbox.command"
    | "context.span"
    | "graph.mutation";
  metadata: Record<string, string | number | boolean | null>;
  lineage: ActivityLineage;
  debug: {
    source: string;
    payload: unknown;
  };
}

export interface ActivityStackItem {
  activity: RunActivity;
  row: number;
  leftPct: number;
  widthPct: number;
}

export interface ActivityBandLayout {
  band: ActivityBand;
  rowCount: number;
}

export interface ActivityStackLayout {
  items: ActivityStackItem[];
  bands: ActivityBandLayout[];
  rowCount: number;
  startMs: number;
  endMs: number;
  maxConcurrency: number;
}
