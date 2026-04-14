"use client";

/**
 * DAGCanvas - React Flow canvas for visualizing task DAGs.
 *
 * Features:
 * - Hierarchical dagre layout with nested container rendering
 * - Depth-based expansion control via DepthSelector
 * - Search/filter tasks by name
 * - Live updates via useRunState hook
 * - Zoom/pan controls
 */

import { useCallback, useEffect, useState, useMemo } from "react";
import {
  ReactFlow,
  Edge,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  ConnectionLineType,
  Panel,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { TaskStatus, type WorkflowRunState } from "@/lib/types";
import { nodeTypes, type TaskNodeType } from "./TaskNode";
import { GraphDelegationEdge } from "./edges/GraphDelegationEdge";
import { GraphDependencyEdge } from "./edges/GraphDependencyEdge";
import { DepthSelector } from "@/features/graph/components/DepthSelector";
import { GraphExpansionProvider } from "@/features/graph/hooks/useGraphExpansion";
import { computeHierarchicalLayout, calculateExpandedContainers } from "@/features/graph/layout/hierarchicalLayout";
import { DEFAULT_EXPANDED_DEPTH } from "@/features/graph/layout/layoutTypes";
import type { ContainerDimensions } from "@/features/graph/layout/layoutTypes";
import { SearchInput } from "@/components/common/SearchInput";

interface DAGCanvasProps {
  runId: string;
  runState: WorkflowRunState | null;
  isLoading?: boolean;
  error?: string | null;
  isSubscribed?: boolean;
  onTaskClick?: (taskId: string) => void;
  selectedTaskId?: string | null;
}

/**
 * Status color for minimap nodes.
 */
const edgeTypes = {
  graphDelegation: GraphDelegationEdge,
  graphDependency: GraphDependencyEdge,
};

function getMinimapNodeColor(node: TaskNodeType): string {
  const status = node.data?.task?.status;
  switch (status) {
    case TaskStatus.COMPLETED:
      return "#22c55e";
    case TaskStatus.RUNNING:
      return "#eab308";
    case TaskStatus.FAILED:
      return "#ef4444";
    case TaskStatus.READY:
      return "#3b82f6";
    case TaskStatus.ABANDONED:
      return "#9ca3af";
    default:
      return "#9ca3af";
  }
}

function DAGCanvasInner({
  runId,
  runState,
  isLoading = false,
  error = null,
  isSubscribed = false,
  onTaskClick,
  selectedTaskId,
}: DAGCanvasProps) {
  const [expandedDepth, setExpandedDepth] = useState<number | "all">(DEFAULT_EXPANDED_DEPTH);
  const [manualExpansions, setManualExpansions] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<TaskNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [containerDims, setContainerDims] = useState<Map<string, ContainerDimensions>>(new Map());
  const [prevTaskIds, setPrevTaskIds] = useState<Set<string>>(new Set());

  const newNodeIds = useMemo(() => {
    if (!runState?.tasks) return new Set<string>();
    if (prevTaskIds.size === 0) return new Set<string>();
    const newIds = new Set<string>();
    for (const id of runState.tasks.keys()) {
      if (!prevTaskIds.has(id)) newIds.add(id);
    }
    return newIds;
  }, [runState?.tasks, prevTaskIds]);

  useEffect(() => {
    if (runState?.tasks) {
      setPrevTaskIds(new Set(runState.tasks.keys()));
    }
  }, [runState?.tasks]);

  // Compute max available depth from tasks
  const maxAvailableDepth = useMemo(() => {
    if (!runState?.tasks) return 0;
    let max = 0;
    for (const task of runState.tasks.values()) {
      max = Math.max(max, task.level);
    }
    return max;
  }, [runState?.tasks]);

  // Compute expanded containers from depth + manual overrides
  const expandedContainers = useMemo(() => {
    if (!runState?.tasks) return new Set<string>();
    const maxDepth = expandedDepth === "all" ? Infinity : expandedDepth;
    const fromDepth = calculateExpandedContainers(runState.tasks, maxDepth);
    // Merge manual expansions (toggled individually)
    for (const id of manualExpansions) {
      if (fromDepth.has(id)) {
        fromDepth.delete(id);
      } else {
        const task = runState.tasks.get(id);
        if (task && task.childIds.length > 0) {
          fromDepth.add(id);
        }
      }
    }
    return fromDepth;
  }, [runState?.tasks, expandedDepth, manualExpansions]);

  // Calculate matching node count
  const matchCount = useMemo(() => {
    if (!searchQuery.trim() || !runState?.tasks) return 0;
    const searchLower = searchQuery.toLowerCase().trim();
    let count = 0;
    for (const task of Array.from(runState.tasks.values())) {
      if (
        task.name.toLowerCase().includes(searchLower) ||
        task.description?.toLowerCase().includes(searchLower) ||
        task.assignedWorkerName?.toLowerCase().includes(searchLower)
      ) {
        count++;
      }
    }
    return count;
  }, [searchQuery, runState?.tasks]);

  // Compute hierarchical layout when data changes
  useEffect(() => {
    if (!runState?.tasks || runState.tasks.size === 0) return;

    const result = computeHierarchicalLayout(
      runState.tasks,
      expandedContainers,
      searchQuery,
      onTaskClick,
      selectedTaskId,
      "LR",
      newNodeIds,
    );

    setNodes(result.nodes as TaskNodeType[]);
    setEdges(result.edges);
    setContainerDims(result.containerDimensions);
  }, [
    runState?.tasks,
    expandedContainers,
    searchQuery,
    onTaskClick,
    selectedTaskId,
    newNodeIds,
    setNodes,
    setEdges,
  ]);

  // Handle depth change — reset manual overrides when depth changes
  const handleDepthChange = useCallback((depth: number | "all") => {
    setExpandedDepth(depth);
    setManualExpansions(new Set());
  }, []);

  // Toggle individual container expansion
  const toggleExpand = useCallback((taskId: string) => {
    setManualExpansions((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) {
        next.delete(taskId);
      } else {
        next.add(taskId);
      }
      return next;
    });
  }, []);

  // Handle search change
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
  }, []);

  const expansionContextValue = useMemo(
    () => ({ expandedContainers, toggleExpand, containerDimensions: containerDims }),
    [expandedContainers, toggleExpand, containerDims],
  );

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900">
        <div className="flex items-center gap-3 text-gray-500 dark:text-gray-400">
          <svg
            className="animate-spin h-5 w-5"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span>Loading DAG...</span>
        </div>
      </div>
    );
  }

  // Error state — only show when we have no data to display
  if (error && (!runState?.tasks || runState.tasks.size === 0)) {
    const isNotFoundError = error.includes("not found");
    return (
      <div className="flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900">
        <div className="text-center max-w-md">
          <div className={`${isNotFoundError ? 'text-amber-500' : 'text-red-500'} dark:${isNotFoundError ? 'text-amber-400' : 'text-red-400'} mb-2`}>
            <svg
              className="w-12 h-12 mx-auto"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              {isNotFoundError ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              )}
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            {isNotFoundError ? "Run Data Unavailable" : "Connection Error"}
          </h3>
          <p className="text-gray-500 dark:text-gray-400">{error}</p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 font-mono">
            Run ID: {runId}
          </p>
        </div>
      </div>
    );
  }

  // Empty state
  if (!runState?.tasks || runState.tasks.size === 0) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="text-gray-400 dark:text-gray-500 mb-2">
            <svg
              className="w-12 h-12 mx-auto"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Waiting for tasks...
          </h3>
          <p className="text-gray-500 dark:text-gray-400">
            {isSubscribed
              ? "Subscribed to run updates. Tasks will appear when the workflow starts."
              : "Connecting to server..."}
          </p>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-2 font-mono">
            Run ID: {runId}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full min-h-[60vh] w-full" data-testid="graph-canvas">
      <GraphExpansionProvider value={expansionContextValue}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          connectionLineType={ConnectionLineType.SmoothStep}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          maxZoom={2}
          defaultEdgeOptions={{}}
          proOptions={{ hideAttribution: true }}
        >
          {/* Background */}
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            className="bg-gray-50 dark:bg-gray-900"
          />

          {/* Controls */}
          <Controls
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm"
            showZoom
            showFitView
            showInteractive={false}
          />

          {/* MiniMap */}
          <MiniMap
            nodeColor={getMinimapNodeColor}
            nodeStrokeWidth={3}
            className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm"
            maskColor="rgba(0, 0, 0, 0.1)"
          />

          {/* Top Left: Depth Selector + Search */}
          <Panel position="top-left" className="m-2 sm:m-4 space-y-2">
            <div className="hidden sm:block">
              <DepthSelector
                tasks={runState.tasks}
                currentDepth={expandedDepth}
                onDepthChange={handleDepthChange}
                maxAvailableDepth={maxAvailableDepth}
              />
            </div>
            <div className="flex items-center gap-2">
              <SearchInput
                value={searchQuery}
                onChange={handleSearchChange}
                placeholder="Search tasks..."
                className="w-40 sm:w-64"
              />
              {searchQuery && (
                <span className="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
                  {matchCount} match{matchCount !== 1 ? "es" : ""}
                </span>
              )}
            </div>
            {/* Depth selector on mobile */}
            <div className="sm:hidden">
              <DepthSelector
                tasks={runState.tasks}
                currentDepth={expandedDepth}
                onDepthChange={handleDepthChange}
                maxAvailableDepth={maxAvailableDepth}
              />
            </div>
          </Panel>

          {/* Run Info Panel */}
          <Panel position="top-right" className="m-2 sm:m-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 px-3 py-2 sm:px-4 sm:py-3">
              <h2 className="font-semibold text-gray-900 dark:text-white truncate max-w-[120px] sm:max-w-[200px] text-sm sm:text-base">
                {runState.name}
              </h2>
              <div className="flex items-center gap-2 sm:gap-4 mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
                <span
                  className={`flex items-center gap-1 ${
                    runState.status === "pending" ||
                    runState.status === "executing" ||
                    runState.status === "evaluating"
                      ? "text-yellow-600 dark:text-yellow-400"
                      : runState.status === "completed"
                        ? "text-green-600 dark:text-green-400"
                        : "text-red-600 dark:text-red-400"
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      runState.status === "pending" ||
                      runState.status === "executing" ||
                      runState.status === "evaluating"
                        ? "bg-yellow-500 animate-pulse"
                        : runState.status === "completed"
                          ? "bg-green-500"
                          : "bg-red-500"
                    }`}
                  />
                  <span className="hidden sm:inline">{runState.status}</span>
                </span>
                {runState.durationSeconds !== null && (
                  <span>{Math.round(runState.durationSeconds)}s</span>
                )}
              </div>
            </div>
          </Panel>
        </ReactFlow>
      </GraphExpansionProvider>
    </div>
  );
}

// Wrapper to provide ReactFlow context
import { ReactFlowProvider } from "@xyflow/react";

export function DAGCanvas(props: DAGCanvasProps) {
  return (
    <ReactFlowProvider>
      <DAGCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
