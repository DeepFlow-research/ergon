"use client";

/**
 * DAGCanvas - React Flow canvas for visualizing task DAGs.
 *
 * Features:
 * - Hierarchical dagre layout with nested container rendering
 * - Depth-based expansion control via floating controls
 * - Search/filter tasks by name
 * - Live updates via useRunState hook
 * - Zoom/pan controls
 */

import { useCallback, useEffect, useState, useMemo, useRef } from "react";
import {
  ReactFlow,
  Edge,
  Background,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ConnectionLineType,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { TaskStatus, type WorkflowRunState } from "@/lib/types";
import { nodeTypes, type TaskNodeType } from "./TaskNode";
import { GraphDependencyEdge } from "./edges/GraphDependencyEdge";
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
  highlightedTaskIds?: ReadonlySet<string>;
}

/**
 * Status color for minimap nodes.
 */
const edgeTypes = {
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
    case TaskStatus.CANCELLED:
      return "#9ca3af";
    default:
      return "#9ca3af";
  }
}

/* ─── Floating control cards ────────────────────────────────────── */

const cardClass =
  "bg-[var(--card)] border border-[var(--line)] rounded-lg shadow-card";

function ZoomControls() {
  const { zoomIn, zoomOut, fitView } = useReactFlow();
  const btn =
    "flex items-center justify-center w-7 h-7 text-sm font-semibold text-[var(--muted)] hover:text-[var(--ink)] hover:bg-[var(--paper)] rounded transition-colors";
  return (
    <div className={`${cardClass} flex items-center`}>
      <button className={btn} onClick={() => zoomIn()} aria-label="Zoom in">
        +
      </button>
      <span className="w-px h-4 bg-[var(--line)]" />
      <button className={btn} onClick={() => zoomOut()} aria-label="Zoom out">
        −
      </button>
      <span className="w-px h-4 bg-[var(--line)]" />
      <button
        className={btn}
        onClick={() => fitView({ padding: 0.2 })}
        aria-label="Fit view"
      >
        ⌂
      </button>
    </div>
  );
}

function DepthSelectorCard({
  maxAvailableDepth,
  currentDepth,
  onDepthChange,
}: {
  maxAvailableDepth: number;
  currentDepth: number | "all";
  onDepthChange: (depth: number | "all") => void;
}) {
  const depths: (number | "all")[] = [];
  for (let i = 1; i <= Math.min(maxAvailableDepth, 3); i++) depths.push(i);
  depths.push("all");

  return (
    <div className={`${cardClass} flex items-center gap-1.5 px-2 py-1`}>
      <span
        className="font-mono uppercase tracking-wider"
        style={{ fontSize: 9, color: "var(--faint)" }}
      >
        Depth
      </span>
      <div className="flex items-center rounded bg-[var(--paper)] p-0.5">
        {depths.map((d) => {
          const isActive = currentDepth === d;
          return (
            <button
              key={String(d)}
              onClick={() => onDepthChange(d)}
              className={`px-2 py-0.5 text-xs font-medium rounded transition-colors ${
                isActive
                  ? "bg-[var(--card)] text-[var(--ink)] shadow-card"
                  : "text-[var(--muted)] hover:text-[var(--ink)]"
              }`}
            >
              {d === "all" ? "all" : d}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function SearchCard({
  searchQuery,
  onSearchChange,
  matchCount,
}: {
  searchQuery: string;
  onSearchChange: (value: string) => void;
  matchCount: number;
}) {
  return (
    <div className={`${cardClass} flex items-center gap-1.5 px-2 py-1`}>
      <span
        className="font-mono uppercase tracking-wider shrink-0"
        style={{ fontSize: 9, color: "var(--faint)" }}
      >
        Search
      </span>
      <SearchInput
        value={searchQuery}
        onChange={onSearchChange}
        placeholder="tasks..."
        className="w-36"
      />
      {searchQuery && (
        <span className="text-[10px] whitespace-nowrap" style={{ color: "var(--faint)" }}>
          {matchCount}
        </span>
      )}
    </div>
  );
}

const LEGEND_ITEMS: { status: string; label: string; cssVar: string }[] = [
  { status: "completed", label: "completed", cssVar: "var(--status-completed)" },
  { status: "running", label: "running", cssVar: "var(--status-running)" },
  { status: "ready", label: "ready", cssVar: "var(--status-ready)" },
  { status: "pending", label: "pending", cssVar: "var(--status-pending)" },
  { status: "failed", label: "failed", cssVar: "var(--status-failed)" },
];

function LegendCard() {
  return (
    <div className={`${cardClass} flex items-center gap-3 px-3 py-1.5`}>
      {LEGEND_ITEMS.map((item) => (
        <div key={item.status} className="flex items-center gap-1.5">
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{ backgroundColor: item.cssVar }}
          />
          <span className="text-[10px] font-medium" style={{ color: "var(--muted)" }}>
            {item.label}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ─── Main canvas ───────────────────────────────────────────────── */

function DAGCanvasInner({
  runId,
  runState,
  isLoading = false,
  error = null,
  isSubscribed = false,
  onTaskClick,
  selectedTaskId,
  highlightedTaskIds = new Set(),
}: DAGCanvasProps) {
  const [expandedDepth, setExpandedDepth] = useState<number | "all">(DEFAULT_EXPANDED_DEPTH);
  const [manualExpansions, setManualExpansions] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<TaskNodeType>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [containerDims, setContainerDims] = useState<Map<string, ContainerDimensions>>(new Map());
  const [prevTaskIds, setPrevTaskIds] = useState<Set<string>>(new Set());
  const { fitView: rfFitView } = useReactFlow();
  const fitViewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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

  const maxAvailableDepth = useMemo(() => {
    if (!runState?.tasks) return 0;
    let max = 0;
    for (const task of runState.tasks.values()) {
      max = Math.max(max, task.level);
    }
    return max;
  }, [runState?.tasks]);

  const expandedContainers = useMemo(() => {
    if (!runState?.tasks) return new Set<string>();
    const maxDepth = expandedDepth === "all" ? Infinity : expandedDepth;
    const fromDepth = calculateExpandedContainers(runState.tasks, maxDepth);
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
      highlightedTaskIds,
    );

    setNodes(result.nodes as TaskNodeType[]);
    setEdges(result.edges);
    setContainerDims(result.containerDimensions);

    if (fitViewTimer.current) clearTimeout(fitViewTimer.current);
    fitViewTimer.current = setTimeout(() => {
      rfFitView({ padding: 0.2, duration: 200 });
    }, 100);
  }, [
    runState?.tasks,
    expandedContainers,
    searchQuery,
    onTaskClick,
    selectedTaskId,
    newNodeIds,
    highlightedTaskIds,
    setNodes,
    setEdges,
    rfFitView,
  ]);

  const handleDepthChange = useCallback((depth: number | "all") => {
    setExpandedDepth(depth);
    setManualExpansions(new Set());
  }, []);

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

  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
  }, []);

  const expansionContextValue = useMemo(
    () => ({ expandedContainers, toggleExpand, containerDimensions: containerDims }),
    [expandedContainers, toggleExpand, containerDims],
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full" style={{ background: "var(--paper)" }}>
        <div className="flex items-center gap-3" style={{ color: "var(--muted)" }}>
          <svg
            className="animate-spin h-5 w-5"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
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

  if (error && (!runState?.tasks || runState.tasks.size === 0)) {
    const isNotFoundError = error.includes("not found");
    return (
      <div className="flex items-center justify-center h-full" style={{ background: "var(--paper)" }}>
        <div className="text-center max-w-md">
          <div className={`${isNotFoundError ? "text-amber-500" : "text-red-500"} mb-2`}>
            <svg className="w-12 h-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
          <h3 className="text-lg font-semibold" style={{ color: "var(--ink)" }}>
            {isNotFoundError ? "Run Data Unavailable" : "Connection Error"}
          </h3>
          <p style={{ color: "var(--muted)" }}>{error}</p>
          <p className="text-xs mt-2 font-mono" style={{ color: "var(--faint)" }}>
            Run ID: {runId}
          </p>
        </div>
      </div>
    );
  }

  if (!runState?.tasks || runState.tasks.size === 0) {
    return (
      <div className="flex items-center justify-center h-full" style={{ background: "var(--paper)" }}>
        <div className="text-center">
          <div className="mb-2" style={{ color: "var(--faint)" }}>
            <svg className="w-12 h-12 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
              />
            </svg>
          </div>
          <h3 className="text-lg font-semibold" style={{ color: "var(--ink)" }}>
            Waiting for tasks...
          </h3>
          <p style={{ color: "var(--muted)" }}>
            {isSubscribed
              ? "Subscribed to run updates. Tasks will appear when the workflow starts."
              : "Connecting to server..."}
          </p>
          <p className="text-xs mt-2 font-mono" style={{ color: "var(--faint)" }}>
            Run ID: {runId}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full" style={{ minHeight: 300 }} data-testid="graph-canvas">
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
          <Background
            variant={BackgroundVariant.Dots}
            gap={20}
            size={1}
            color="var(--line)"
            style={{ backgroundColor: "var(--paper)" }}
          />

          <MiniMap
            nodeColor={getMinimapNodeColor}
            nodeStrokeWidth={3}
            className="hidden 2xl:block"
            maskColor="rgba(0, 0, 0, 0.1)"
            style={{
              backgroundColor: "var(--card)",
              border: "1px solid var(--line)",
              borderRadius: 8,
            }}
          />
        </ReactFlow>

        {/* Floating controls — top-left */}
        <div
          className="absolute top-3 left-3 flex items-start gap-2"
          style={{ zIndex: 5 }}
        >
          <ZoomControls />
          <DepthSelectorCard
            maxAvailableDepth={maxAvailableDepth}
            currentDepth={expandedDepth}
            onDepthChange={handleDepthChange}
          />
          <SearchCard
            searchQuery={searchQuery}
            onSearchChange={handleSearchChange}
            matchCount={matchCount}
          />
        </div>

        {/* Floating controls — bottom-left */}
        <div
          className="absolute bottom-3 left-3"
          style={{ zIndex: 5 }}
        >
          <LegendCard />
        </div>
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
