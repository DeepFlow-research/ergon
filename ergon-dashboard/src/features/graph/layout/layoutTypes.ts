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
/**
 * Reserved vertical space at the top of a container node for its header bar.
 *
 * The header in ``ContainerNode`` renders status badge + label + name + timing
 * within a ``px-3 py-2`` flex row (content height ~20px for the status circle,
 * plus 16px of vertical padding and a 1px border). Allowing 56px leaves a safe
 * buffer for the 2px outer dashed border, potential focus ring, and ensures
 * the first child row (e.g. "PENDING" status text in ``LeafNode``) is never
 * clipped by the header.
 *
 * NOTE: This is hardcoded — if the header layout changes substantially
 * (e.g. multi-line name, larger status badge) reconsider this value.
 */
export const CONTAINER_HEADER_HEIGHT = 56;
export const CONTAINER_PADDING = 20;
export const DEFAULT_EXPANDED_DEPTH = 2;
export const MAX_VISIBLE_NODES = 150;

export function getNodeVariant(depth: number): keyof typeof NODE_VARIANTS {
  if (depth <= 1) return "full";
  if (depth === 2) return "standard";
  return "compact";
}
