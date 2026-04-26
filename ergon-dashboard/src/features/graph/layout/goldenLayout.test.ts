import assert from "node:assert/strict";
import test from "node:test";
import type { Node } from "@xyflow/react";

import fixture from "../../../../tests/fixtures/mas-runs/concurrent-mas-run.json";
import { parseGraphMutationDtoArray } from "@/features/graph/contracts/graphMutations";
import { replayToSequence } from "@/features/graph/state/graphMutationReducer";
import { deserializeRunState } from "@/lib/runState";
import type { WorkflowRunState } from "@/lib/types";
import { calculateExpandedContainers, computeHierarchicalLayout } from "./hierarchicalLayout";
import { NODE_VARIANTS, getNodeVariant } from "./layoutTypes";

interface Rect {
  id: string;
  parentId: string | undefined;
  x: number;
  y: number;
  width: number;
  height: number;
}

function emptyRunStateFrom(runState: WorkflowRunState): WorkflowRunState {
  return {
    ...runState,
    tasks: new Map(),
    totalTasks: 0,
    totalLeafTasks: 0,
    completedTasks: 0,
    runningTasks: 0,
    failedTasks: 0,
    edges: new Map(),
    annotationsByTarget: new Map(),
    unhandledMutations: [],
  };
}

function rectFor(node: Node): Rect {
  const task = (node.data as { task?: { level: number } }).task;
  const variant = getNodeVariant(task?.level ?? 1);
  const style = node.style as { width?: number; height?: number } | undefined;
  return {
    id: node.id,
    parentId: node.parentId,
    x: node.position.x,
    y: node.position.y,
    width: Number(style?.width ?? NODE_VARIANTS[variant].width),
    height: Number(style?.height ?? NODE_VARIANTS[variant].height),
  };
}

function overlaps(a: Rect, b: Rect): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

function overlappingSiblingPairs(nodes: Node[]): Array<[string, string]> {
  const rects = nodes.map(rectFor);
  const pairs: Array<[string, string]> = [];
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      if (rects[i].parentId !== rects[j].parentId) continue;
      if (overlaps(rects[i], rects[j])) pairs.push([rects[i].id, rects[j].id]);
    }
  }
  return pairs;
}

test("golden layout renders the full recursive graph without overlapping sibling boxes", () => {
  const runState = deserializeRunState(fixture.runState);
  const mutations = parseGraphMutationDtoArray(fixture.mutations);
  const checkpoint = fixture.checkpoints.find((entry) => entry.sequence === 14);
  assert.ok(checkpoint);
  const displayState = replayToSequence(
    mutations,
    checkpoint.sequence,
    emptyRunStateFrom(runState),
    new Map(),
  );
  const result = computeHierarchicalLayout(
    displayState.tasks,
    calculateExpandedContainers(displayState.tasks, Infinity),
    "",
    undefined,
    null,
    "LR",
    new Set(),
  );

  assert.deepEqual(new Set(result.nodes.map((node) => node.id)), new Set(checkpoint.expectedTaskIds));
  assert.deepEqual(overlappingSiblingPairs(result.nodes), []);
});
