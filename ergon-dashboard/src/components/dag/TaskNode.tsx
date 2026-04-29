"use client";

/**
 * TaskNode - Custom react-flow node component for tasks.
 *
 * Delegates to ContainerNode (expanded containers) or LeafNode (everything else).
 * The rendering variant is determined by depth and expansion state.
 */

import { memo } from "react";
import { type Node, type NodeProps } from "@xyflow/react";
import type { TaskState } from "@/lib/types";
import type { EvaluationRollup } from "@/features/evaluation/contracts";
import { useGraphExpansion } from "@/features/graph/hooks/useGraphExpansion";
import { getNodeVariant } from "@/features/graph/layout/layoutTypes";
import { ContainerNode } from "@/features/graph/components/ContainerNode";
import { LeafNode } from "@/features/graph/components/LeafNode";

export type TaskNodeData = {
  task: TaskState;
  onClick?: (taskId: string) => void;
  selected?: boolean;
  dimmed?: boolean;
  highlighted?: boolean;
  /** True when this node appeared since the previous graph state update (not initial load). */
  isNew?: boolean;
  /** Max ``task.level`` in the run — for depth accent palette. */
  maxGraphDepth?: number;
  /** Dagre rank direction used for this layout pass (drives handle positions). */
  graphLayoutDirection?: "TB" | "LR";
  evaluationRollup?: EvaluationRollup | null;
  evaluationLensActive?: boolean;
};

export type TaskNodeType = Node<TaskNodeData, "taskNode">;

function TaskNodeComponent({ data }: NodeProps<TaskNodeType>) {
  const {
    task,
    onClick,
    selected = false,
    dimmed = false,
    highlighted = false,
    isNew = false,
    maxGraphDepth,
    graphLayoutDirection = "LR",
    evaluationRollup = null,
    evaluationLensActive = false,
  } = data;
  const { expandedContainers, toggleExpand, containerDimensions } = useGraphExpansion();

  const isContainer = task.childIds.length > 0;
  const isExpanded = expandedContainers.has(task.id);

  const spawnHighlight = isNew ? (
    <div
      className="absolute inset-0 z-10 rounded-lg ring-2 ring-blue-400 animate-pulse pointer-events-none"
      style={{ animationDuration: "1s", animationIterationCount: 3 }}
    />
  ) : null;

  if (isContainer && isExpanded) {
    const dims = containerDimensions.get(task.id);
    return (
      <div className="relative h-full w-full">
        {spawnHighlight}
        <ContainerNode
          task={task}
          isExpanded
          onToggleExpand={toggleExpand}
          onClick={onClick}
          selected={selected}
          dimmed={dimmed}
          highlighted={highlighted}
          containerWidth={dims?.width ?? 260}
          containerHeight={dims?.height ?? 100}
          layoutDirection={graphLayoutDirection}
          maxGraphDepth={maxGraphDepth}
          evaluationRollup={evaluationRollup}
          evaluationLensActive={evaluationLensActive}
        />
      </div>
    );
  }

  const variant = getNodeVariant(task.level);
  return (
    <div className="relative h-full w-full">
      {spawnHighlight}
      <LeafNode
        task={task}
        variant={variant}
        onClick={onClick}
        selected={selected}
        dimmed={dimmed}
        highlighted={highlighted}
        layoutDirection={graphLayoutDirection}
        maxGraphDepth={maxGraphDepth}
        evaluationRollup={evaluationRollup}
        evaluationLensActive={evaluationLensActive}
      />
    </div>
  );
}

export const TaskNode = memo(TaskNodeComponent);

export const nodeTypes = {
  taskNode: TaskNode,
};
