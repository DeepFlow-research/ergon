"use client";

import {
  BaseEdge,
  EdgeLabelRenderer,
  getStraightPath,
  type EdgeProps,
} from "@xyflow/react";

export type GraphDependencyEdgeData = {
  stroke: string;
  strokeWidth?: number;
  strokeDasharray?: string;
  opacity?: number;
};

export function GraphDependencyEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  selected,
  animated,
}: EdgeProps) {
  const d = (data ?? {}) as GraphDependencyEdgeData;
  const [edgePath, labelX, labelY] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });
  const baseW = d.strokeWidth ?? 3;
  const strokeWidth = baseW + (selected ? 1 : 0);
  const angle = Math.atan2(targetY - sourceY, targetX - sourceX);

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        interactionWidth={22}
        style={{
          stroke: d.stroke,
          strokeWidth,
          strokeDasharray: d.strokeDasharray ?? "5,5",
          opacity: d.opacity ?? 1,
        }}
        className={animated ? "ergon-edge-animated" : undefined}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan pointer-events-none"
          style={{
            position: "absolute",
            transform: `translate(${labelX}px,${labelY}px) translate(-50%, -50%) rotate(${angle}rad)`,
          }}
          aria-hidden
        >
          <svg width={12} height={12} viewBox="0 0 10 10">
            <polygon points="0,1 9,5 0,9" fill={d.stroke} opacity={0.85} />
          </svg>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
