import dagre from "dagre";
import type { Edge } from "@xyflow/react";
import type { TaskState } from "@/lib/types";
import type { TaskNodeType } from "@/components/dag/TaskNode";
import {
  type ContainerDimensions,
  type LayoutedGraph,
  NODE_VARIANTS,
  MIN_CONTAINER_WIDTH,
  MIN_CONTAINER_HEIGHT,
  CONTAINER_HEADER_HEIGHT,
  CONTAINER_PADDING,
  getNodeVariant,
  MAX_VISIBLE_NODES,
} from "./layoutTypes";
import { layoutNodesInGrid, shouldLayoutChildrenAsGrid } from "./gridLayout";

function _expandAtDepth(tasks: Map<string, TaskState>, maxDepth: number): Set<string> {
  const expanded = new Set<string>();
  for (const task of tasks.values()) {
    if (task.childIds.length > 0 && task.level < maxDepth) {
      expanded.add(task.id);
    }
  }
  return expanded;
}

function _countVisibleNodes(tasks: Map<string, TaskState>, expanded: Set<string>): number {
  let count = 0;
  for (const task of tasks.values()) {
    if (task.parentId === null || expanded.has(task.parentId)) {
      count++;
    }
  }
  return count;
}

/**
 * Determine which containers should be expanded based on a maximum depth.
 * A container is expanded if it has children and its level is below maxDepth.
 * When ``maxDepth`` is ``Infinity`` (expand all), no cap is applied.
 */
export function calculateExpandedContainers(
  tasks: Map<string, TaskState>,
  maxDepth: number,
): Set<string> {
  if (maxDepth === Infinity) {
    return _expandAtDepth(tasks, maxDepth);
  }

  let depth = maxDepth;
  let expanded = _expandAtDepth(tasks, depth);

  while (_countVisibleNodes(tasks, expanded) > MAX_VISIBLE_NODES && depth > 0) {
    depth -= 1;
    expanded = _expandAtDepth(tasks, depth);
  }

  return expanded;
}

const REMOVED_EDGE_OPACITY = 0.3;
const REMOVED_EDGE_STROKE = "#d1d5db";
const DEP_SATISFIED_STROKE = "#22c55e";
const DEP_DEFAULT_STROKE = "#94a3b8";
const DELEGATION_ACTIVE_STROKE = "#3b82f6";
const DELEGATION_DEFAULT_STROKE = "#94a3b8";

function isEdgeFadedForRemovedOrCancelled(a?: TaskState, b?: TaskState): boolean {
  const statuses = [a?.status, b?.status].map((s) => (s == null ? "" : String(s)));
  return statuses.some((s) => s === "cancelled" || s === "removed");
}

function searchDimmed(
  searchLower: string,
  matchingNodeIds: Set<string>,
  idA: string,
  idB: string,
): boolean {
  return Boolean(
    searchLower && !matchingNodeIds.has(idA) && !matchingNodeIds.has(idB),
  );
}

function dependencyEdgeStyle(
  source: TaskState | undefined,
  target: TaskState | undefined,
  searchLower: string,
  matchingNodeIds: Set<string>,
  sourceId: string,
  targetId: string,
): { stroke: string; strokeDasharray: string; opacity: number; animated?: boolean } {
  const faded = isEdgeFadedForRemovedOrCancelled(source, target);
  const dimmed = searchDimmed(searchLower, matchingNodeIds, sourceId, targetId);
  const satisfied = source?.status === "completed";
  return {
    stroke: faded ? REMOVED_EDGE_STROKE : satisfied ? DEP_SATISFIED_STROKE : DEP_DEFAULT_STROKE,
    strokeDasharray: "5,5",
    opacity: faded ? REMOVED_EDGE_OPACITY : dimmed ? 0.3 : 1,
    animated: target?.status === "running",
  };
}

function delegationEdgeStyle(
  parent: TaskState | undefined,
  child: TaskState | undefined,
  searchLower: string,
  matchingNodeIds: Set<string>,
  parentId: string,
  childId: string,
): { stroke: string; strokeWidth: number; opacity: number; animated?: boolean } {
  const faded = isEdgeFadedForRemovedOrCancelled(parent, child);
  const dimmed = searchDimmed(searchLower, matchingNodeIds, parentId, childId);
  const active =
    child?.status === "running" ||
    child?.status === "ready" ||
    parent?.status === "running";
  return {
    stroke: faded ? REMOVED_EDGE_STROKE : active ? DELEGATION_ACTIVE_STROKE : DELEGATION_DEFAULT_STROKE,
    strokeWidth: 3,
    opacity: faded ? REMOVED_EDGE_OPACITY : dimmed ? 0.3 : 1,
    animated: child?.status === "running",
  };
}

function computeMaxGraphDepth(tasks: Map<string, TaskState>): number {
  let m = 0;
  for (const t of tasks.values()) {
    m = Math.max(m, t.level);
  }
  return m;
}

/**
 * Run dagre on a set of nodes and return their positions.
 * Used for both root-level and per-container layout passes.
 */
function runDagreLayout(
  nodeIds: string[],
  nodeSizes: Map<string, { width: number; height: number }>,
  edges: Array<{ source: string; target: string }>,
  direction: "TB" | "LR" = "TB",
): Map<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: direction,
    nodesep: 50,
    ranksep: 50,
    edgesep: 20,
    marginx: 0,
    marginy: 0,
    acyclicer: "greedy",
    ranker: "network-simplex",
    align: "UL",
  });

  for (const id of nodeIds) {
    const size = nodeSizes.get(id) ?? { width: 180, height: 90 };
    g.setNode(id, { width: size.width, height: size.height });
  }

  for (const edge of edges) {
    if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
      g.setEdge(edge.source, edge.target);
    }
  }

  dagre.layout(g);

  const positions = new Map<string, { x: number; y: number }>();
  for (const id of nodeIds) {
    const node = g.node(id);
    if (node) {
      const size = nodeSizes.get(id) ?? { width: 180, height: 90 };
      positions.set(id, {
        x: node.x - size.width / 2,
        y: node.y - size.height / 2,
      });
    }
  }

  return positions;
}

/**
 * Compute bounding box from positioned nodes.
 */
function computeBoundingBox(
  positions: Map<string, { x: number; y: number }>,
  sizes: Map<string, { width: number; height: number }>,
): { width: number; height: number } {
  let maxX = 0;
  let maxY = 0;

  for (const [id, pos] of positions) {
    const size = sizes.get(id) ?? { width: 180, height: 90 };
    maxX = Math.max(maxX, pos.x + size.width);
    maxY = Math.max(maxY, pos.y + size.height);
  }

  return { width: maxX, height: maxY };
}

/**
 * Get the depth of a container (max depth of any descendant).
 */
function getContainerDepth(
  taskId: string,
  tasks: Map<string, TaskState>,
  expandedContainers: Set<string>,
): number {
  const task = tasks.get(taskId);
  if (!task || task.childIds.length === 0 || !expandedContainers.has(taskId)) {
    return 0;
  }
  let maxChildDepth = 0;
  for (const childId of task.childIds) {
    maxChildDepth = Math.max(
      maxChildDepth,
      1 + getContainerDepth(childId, tasks, expandedContainers),
    );
  }
  return maxChildDepth;
}

/**
 * Compute hierarchical layout for a task graph with nested containers.
 *
 * Bottom-up: deepest containers are laid out first. Their computed dimensions
 * feed into the parent's dagre pass. Returns React Flow nodes with correct
 * positions (local to parent for nested, global for root-level).
 */
export function computeHierarchicalLayout(
  tasks: Map<string, TaskState>,
  expandedContainers: Set<string>,
  searchQuery: string,
  onTaskClick?: (taskId: string) => void,
  selectedTaskId?: string | null,
  direction: "TB" | "LR" = "LR",
  newNodeIds: ReadonlySet<string> = new Set(),
): LayoutedGraph {
  const containerDimensions = new Map<string, ContainerDimensions>();
  const allNodes: TaskNodeType[] = [];
  const allEdges: Edge[] = [];
  const maxGraphDepth = computeMaxGraphDepth(tasks);

  const searchLower = searchQuery.toLowerCase().trim();
  const matchingNodeIds = new Set<string>();

  if (searchLower) {
    for (const task of tasks.values()) {
      if (
        task.name.toLowerCase().includes(searchLower) ||
        task.description?.toLowerCase().includes(searchLower) ||
        task.assignedWorkerName?.toLowerCase().includes(searchLower)
      ) {
        matchingNodeIds.add(task.id);
      }
    }
  }

  // Collect all expanded containers sorted by depth (deepest first)
  const expandedList: Array<{ id: string; depth: number }> = [];
  for (const containerId of expandedContainers) {
    const task = tasks.get(containerId);
    if (task && task.childIds.length > 0) {
      expandedList.push({
        id: containerId,
        depth: getContainerDepth(containerId, tasks, expandedContainers),
      });
    }
  }
  expandedList.sort((a, b) => b.depth - a.depth);

  // Effective sizes for all tasks (starts with leaf sizes, containers get updated)
  const effectiveSizes = new Map<string, { width: number; height: number }>();
  for (const task of tasks.values()) {
    const variant = getNodeVariant(task.level);
    effectiveSizes.set(task.id, { ...NODE_VARIANTS[variant] });
  }

  // Process each expanded container bottom-up
  for (const { id: containerId } of expandedList) {
    const containerTask = tasks.get(containerId);
    if (!containerTask) continue;

    const childIds = containerTask.childIds.filter((cid) => tasks.has(cid));
    if (childIds.length === 0) continue;

    const childSizes = new Map<string, { width: number; height: number }>();
    for (const cid of childIds) {
      childSizes.set(cid, effectiveSizes.get(cid) ?? { width: 180, height: 90 });
    }

    // Collect edges among direct children (dependency edges)
    const childEdges: Array<{ source: string; target: string }> = [];
    const childIdSet = new Set(childIds);
    for (const cid of childIds) {
      const childTask = tasks.get(cid);
      if (!childTask) continue;
      for (const depId of childTask.dependsOnIds) {
        if (childIdSet.has(depId)) {
          childEdges.push({ source: depId, target: cid });
        }
      }
    }

    const localPositions = shouldLayoutChildrenAsGrid(childIds.length, childEdges.length)
      ? layoutNodesInGrid(childIds, childSizes, 0, 0)
      : runDagreLayout(childIds, childSizes, childEdges, direction);

    // Compute bounding box
    const bbox = computeBoundingBox(localPositions, childSizes);

    // Container dimensions = bbox + padding + header
    const containerWidth = Math.max(
      MIN_CONTAINER_WIDTH,
      bbox.width + CONTAINER_PADDING * 2,
    );
    const containerHeight = Math.max(
      MIN_CONTAINER_HEIGHT,
      bbox.height + CONTAINER_HEADER_HEIGHT + CONTAINER_PADDING * 2,
    );

    containerDimensions.set(containerId, {
      width: containerWidth,
      height: containerHeight,
    });
    effectiveSizes.set(containerId, {
      width: containerWidth,
      height: containerHeight,
    });

    // Create React Flow nodes for children (positioned relative to parent)
    for (const cid of childIds) {
      const childTask = tasks.get(cid);
      if (!childTask) continue;

      const localPos = localPositions.get(cid) ?? { x: 0, y: 0 };
      const isMatch = !searchLower || matchingNodeIds.has(cid);

      allNodes.push({
        id: cid,
        type: "taskNode",
        position: {
          x: localPos.x + CONTAINER_PADDING,
          y: localPos.y + CONTAINER_HEADER_HEIGHT + CONTAINER_PADDING,
        },
        parentId: containerId,
        extent: "parent" as const,
        data: {
          task: childTask,
          onClick: onTaskClick,
          selected: cid === selectedTaskId,
          dimmed: searchLower ? !isMatch : false,
          highlighted: searchLower ? isMatch : false,
          isNew: newNodeIds.has(cid),
          maxGraphDepth,
          graphLayoutDirection: direction,
        },
      });
    }

    // Create edges among children within this container
    for (const cid of childIds) {
      const childTask = tasks.get(cid);
      if (!childTask) continue;
      for (const depId of childTask.dependsOnIds) {
        if (childIdSet.has(depId)) {
          const edgeId = `${depId}->${cid}`;
          const depTask = tasks.get(depId);
          const depStyle = dependencyEdgeStyle(
            depTask,
            childTask,
            searchLower,
            matchingNodeIds,
            depId,
            cid,
          );
          allEdges.push({
            id: edgeId,
            source: depId,
            target: cid,
            type: "graphDependency",
            animated: Boolean(depStyle.animated),
            data: {
              stroke: depStyle.stroke,
              strokeWidth: 3,
              strokeDasharray: depStyle.strokeDasharray,
              opacity: depStyle.opacity,
            },
          });
        }
      }
    }
  }

  // Identify root-level nodes: parentId === null OR parent not expanded
  const rootNodeIds: string[] = [];
  const processedChildIds = new Set(allNodes.map((n) => n.id));

  for (const task of tasks.values()) {
    if (processedChildIds.has(task.id)) continue;
    const isRoot =
      task.parentId === null || !expandedContainers.has(task.parentId);
    if (isRoot) {
      rootNodeIds.push(task.id);
    }
  }

  // Collect edges among root-level nodes
  const rootEdges: Array<{ source: string; target: string }> = [];
  const rootIdSet = new Set(rootNodeIds);
  for (const taskId of rootNodeIds) {
    const task = tasks.get(taskId);
    if (!task) continue;

    // Parent-child edges (only for collapsed containers at root level)
    for (const childId of task.childIds) {
      if (rootIdSet.has(childId)) {
        rootEdges.push({ source: task.id, target: childId });
      }
    }

    // Dependency edges
    for (const depId of task.dependsOnIds) {
      if (rootIdSet.has(depId)) {
        rootEdges.push({ source: depId, target: task.id });
      }
    }
  }

  // Root-level dagre pass
  const rootSizes = new Map<string, { width: number; height: number }>();
  for (const id of rootNodeIds) {
    rootSizes.set(id, effectiveSizes.get(id) ?? { width: 180, height: 90 });
  }

  const rootPositions = runDagreLayout(
    rootNodeIds,
    rootSizes,
    rootEdges,
    direction,
  );

  // Create React Flow nodes for root level
  for (const taskId of rootNodeIds) {
    const task = tasks.get(taskId);
    if (!task) continue;

    const globalPos = rootPositions.get(taskId) ?? { x: 0, y: 0 };
    const isMatch = !searchLower || matchingNodeIds.has(taskId);

    allNodes.push({
      id: taskId,
      type: "taskNode",
      position: globalPos,
      data: {
        task,
        onClick: onTaskClick,
        selected: taskId === selectedTaskId,
        dimmed: searchLower ? !isMatch : false,
        highlighted: searchLower ? isMatch : false,
        isNew: newNodeIds.has(taskId),
        maxGraphDepth,
        graphLayoutDirection: direction,
      },
      // Container nodes need explicit dimensions so React Flow sizes them
      ...(expandedContainers.has(taskId) && containerDimensions.has(taskId)
        ? {
            style: {
              width: containerDimensions.get(taskId)!.width,
              height: containerDimensions.get(taskId)!.height,
            },
          }
        : {}),
    });
  }

  // Create root-level edges
  for (const taskId of rootNodeIds) {
    const task = tasks.get(taskId);
    if (!task) continue;

    for (const childId of task.childIds) {
      if (rootIdSet.has(childId)) {
        const childTask = tasks.get(childId);
        const delStyle = delegationEdgeStyle(
          task,
          childTask,
          searchLower,
          matchingNodeIds,
          taskId,
          childId,
        );
        allEdges.push({
          id: `${taskId}->${childId}`,
          source: taskId,
          target: childId,
          type: "graphDependency",
          animated: Boolean(delStyle.animated),
          data: {
            stroke: delStyle.stroke,
            strokeWidth: delStyle.strokeWidth,
            strokeDasharray: "none",
            opacity: delStyle.opacity,
          },
        });
      }
    }

    for (const depId of task.dependsOnIds) {
      if (rootIdSet.has(depId)) {
        const edgeId = `${depId}->${taskId}`;
        if (!allEdges.some((e) => e.id === edgeId)) {
          const depTask = tasks.get(depId);
          const depStyle = dependencyEdgeStyle(
            depTask,
            task,
            searchLower,
            matchingNodeIds,
            depId,
            taskId,
          );
          allEdges.push({
            id: edgeId,
            source: depId,
            target: taskId,
            type: "graphDependency",
            animated: Boolean(depStyle.animated),
            data: {
              stroke: depStyle.stroke,
              strokeWidth: 3,
              strokeDasharray: depStyle.strokeDasharray,
              opacity: depStyle.opacity,
            },
          });
        }
      }
    }
  }

  // Ensure container nodes are ordered before their children for React Flow
  const containerIds = new Set(expandedContainers);
  const sortedNodes = allNodes.sort((a, b) => {
    const aIsContainer = containerIds.has(a.id);
    const bIsContainer = containerIds.has(b.id);
    if (aIsContainer && !bIsContainer) return -1;
    if (!aIsContainer && bIsContainer) return 1;

    // Among containers, parents before children (lower level first)
    if (aIsContainer && bIsContainer) {
      const aLevel = (a.data as { task: TaskState }).task.level;
      const bLevel = (b.data as { task: TaskState }).task.level;
      return aLevel - bLevel;
    }
    return 0;
  });

  return {
    nodes: sortedNodes,
    edges: allEdges,
    containerDimensions,
  };
}
