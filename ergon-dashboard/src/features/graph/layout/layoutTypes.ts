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
  full: { width: 190, height: 88 },
  standard: { width: 160, height: 64 },
  compact: { width: 122, height: 46 },
} as const;

export const MIN_CONTAINER_WIDTH = 240;
export const MIN_CONTAINER_HEIGHT = 92;
export const CONTAINER_HEADER_HEIGHT = 32;
export const CONTAINER_PADDING = 16;
export const DEFAULT_EXPANDED_DEPTH = 2;
export const MAX_VISIBLE_NODES = 150;

export function getNodeVariant(depth: number): keyof typeof NODE_VARIANTS {
  if (depth <= 1) return "full";
  if (depth === 2) return "standard";
  return "compact";
}
