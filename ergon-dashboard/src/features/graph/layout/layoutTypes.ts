import type { Node, Edge } from "@xyflow/react";

export interface ContainerDimensions {
  width: number;
  height: number;
}

export interface LayoutResult {
  localPositions: Map<string, { x: number; y: number }>;
  containerSize: ContainerDimensions;
}

export interface LayoutedGraph {
  nodes: Node[];
  edges: Edge[];
  containerDimensions: Map<string, ContainerDimensions>;
}

export const NODE_VARIANTS = {
  full: { width: 220, height: 120 },
  standard: { width: 180, height: 90 },
  compact: { width: 140, height: 50 },
} as const;

export const MIN_CONTAINER_WIDTH = 260;
export const MIN_CONTAINER_HEIGHT = 100;
export const CONTAINER_HEADER_HEIGHT = 50;
export const CONTAINER_PADDING = 20;
export const DEFAULT_EXPANDED_DEPTH = 2;
export const MAX_VISIBLE_NODES = 150;

export function getNodeVariant(depth: number): keyof typeof NODE_VARIANTS {
  if (depth <= 1) return "full";
  if (depth === 2) return "standard";
  return "compact";
}
