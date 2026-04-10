"use client";

/**
 * DAGCanvas - React Flow canvas for visualizing task DAGs.
 *
 * Features:
 * - Automatic dagre layout for hierarchical task display
 * - Level filtering via LevelSelector
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
import dagre from "dagre";
import "@xyflow/react/dist/style.css";

import { TaskState, TaskStatus, WorkflowRunState } from "@/lib/types";
import { nodeTypes, type TaskNodeType } from "./TaskNode";
import { LevelSelector } from "./LevelSelector";
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

// Node dimensions for dagre layout
const NODE_WIDTH = 220;
const NODE_HEIGHT = 120;

/**
 * Apply dagre layout to nodes and edges.
 */
function getLayoutedElements(
  nodes: TaskNodeType[],
  edges: Edge[],
  direction: "TB" | "LR" = "TB"
) {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  dagreGraph.setGraph({
    rankdir: direction,
    nodesep: 50,
    ranksep: 80,
    edgesep: 20,
  });

  // Add nodes to dagre graph
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });

  // Add edges to dagre graph
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Run dagre layout
  dagre.layout(dagreGraph);

  // Apply positions from dagre
  const layoutedNodes: TaskNodeType[] = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

/**
 * Convert task map to react-flow nodes and edges.
 */
function tasksToFlowElements(
  tasks: Map<string, TaskState>,
  selectedLevel: number | null,
  searchQuery: string,
  onTaskClick?: (taskId: string) => void,
  selectedTaskId?: string | null,
): { nodes: TaskNodeType[]; edges: Edge[]; matchingNodeIds: Set<string> } {
  const nodes: TaskNodeType[] = [];
  const edges: Edge[] = [];

  // Filter tasks by level if needed
  const filteredTasks = selectedLevel !== null
    ? Array.from(tasks.values()).filter((t) => t.level === selectedLevel)
    : Array.from(tasks.values());

  const filteredTaskIds = new Set(filteredTasks.map((t) => t.id));

  // Find matching task IDs based on search query
  const searchLower = searchQuery.toLowerCase().trim();
  const matchingNodeIds = new Set<string>();
  
  if (searchLower) {
    for (const task of filteredTasks) {
      if (
        task.name.toLowerCase().includes(searchLower) ||
        task.description?.toLowerCase().includes(searchLower) ||
        task.assignedWorkerName?.toLowerCase().includes(searchLower)
      ) {
        matchingNodeIds.add(task.id);
      }
    }
  }

  // Create nodes
  for (const task of filteredTasks) {
    const isMatch = !searchLower || matchingNodeIds.has(task.id);
    nodes.push({
      id: task.id,
      type: "taskNode",
      position: { x: 0, y: 0 }, // Will be set by dagre
      data: {
        task,
        onClick: onTaskClick,
        selected: task.id === selectedTaskId,
        dimmed: searchLower ? !isMatch : false,
        highlighted: searchLower ? isMatch : false,
      },
    });
  }

  // Create edges (only between visible tasks)
  for (const task of filteredTasks) {
    // Parent-child edges
    for (const childId of task.childIds) {
      if (filteredTaskIds.has(childId)) {
        edges.push({
          id: `${task.id}->${childId}`,
          source: task.id,
          target: childId,
          type: "smoothstep",
          animated: tasks.get(childId)?.status === TaskStatus.RUNNING,
          style: {
            stroke:
              tasks.get(childId)?.status === TaskStatus.RUNNING
                ? "#eab308"
                : "#94a3b8",
            strokeWidth: 2,
            opacity: searchLower && !matchingNodeIds.has(task.id) && !matchingNodeIds.has(childId) ? 0.3 : 1,
          },
        });
      }
    }

    // Dependency edges (if viewing all levels or same level)
    for (const depId of task.dependsOnIds) {
      if (filteredTaskIds.has(depId)) {
        // Check if this edge already exists (avoid duplicates)
        const edgeId = `${depId}->${task.id}`;
        if (!edges.some((e) => e.id === edgeId)) {
          edges.push({
            id: edgeId,
            source: depId,
            target: task.id,
            type: "smoothstep",
            animated: task.status === TaskStatus.RUNNING,
            style: {
              stroke:
                task.status === TaskStatus.RUNNING ? "#eab308" : "#94a3b8",
              strokeWidth: 2,
              strokeDasharray: "5,5", // Dashed for dependency edges
              opacity: searchLower && !matchingNodeIds.has(task.id) && !matchingNodeIds.has(depId) ? 0.3 : 1,
            },
          });
        }
      }
    }
  }

  return { nodes, edges, matchingNodeIds };
}

/**
 * Status color for minimap nodes.
 */
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
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<TaskNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

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

  // Convert tasks to flow elements when data changes
  useEffect(() => {
    if (!runState?.tasks || runState.tasks.size === 0) return;

    const { nodes: rawNodes, edges: rawEdges } = tasksToFlowElements(
      runState.tasks,
      selectedLevel,
      searchQuery,
      onTaskClick,
      selectedTaskId,
    );

    // Apply dagre layout
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
      rawNodes,
      rawEdges
    );

    setNodes(layoutedNodes);
    setEdges(layoutedEdges);
  }, [runState?.tasks, selectedLevel, searchQuery, onTaskClick, selectedTaskId, setNodes, setEdges]);

  // Handle level change
  const handleLevelChange = useCallback((level: number | null) => {
    setSelectedLevel(level);
  }, []);

  // Handle search change
  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
  }, []);

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

  // Error state
  if (error) {
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
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        connectionLineType={ConnectionLineType.SmoothStep}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.1}
        maxZoom={2}
        defaultEdgeOptions={{
          type: "smoothstep",
          style: { strokeWidth: 2 },
        }}
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

        {/* Top Left: Level Selector + Search */}
        <Panel position="top-left" className="m-2 sm:m-4 space-y-2">
          <div className="hidden sm:block">
            <LevelSelector
              tasks={runState.tasks}
              selectedLevel={selectedLevel}
              onChange={handleLevelChange}
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
          {/* Level selector on mobile - simplified */}
          <div className="sm:hidden">
            <LevelSelector
              tasks={runState.tasks}
              selectedLevel={selectedLevel}
              onChange={handleLevelChange}
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
