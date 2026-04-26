import type { RunEventKind } from "@/lib/runEvents";

export type ActivityKind =
  | "execution"
  | "graph"
  | "message"
  | "artifact"
  | "evaluation"
  | "context"
  | "sandbox";

export interface RunActivity {
  id: string;
  kind: ActivityKind;
  label: string;
  taskId: string | null;
  sequence: number | null;
  startAt: string;
  endAt: string | null;
  isInstant: boolean;
  actor: string | null;
  sourceKind: RunEventKind | "execution.span" | "sandbox.span" | "graph.mutation";
  metadata: Record<string, string | number | boolean | null>;
}

export interface ActivityStackItem {
  activity: RunActivity;
  row: number;
  leftPct: number;
  widthPct: number;
}

export interface ActivityStackLayout {
  items: ActivityStackItem[];
  rowCount: number;
  startMs: number;
  endMs: number;
  maxConcurrency: number;
}
