"use client";

import { useEffect, useState } from "react";
import type { Layout } from "react-resizable-panels";

const VERTICAL_LAYOUT_STORAGE_KEY = "ergon-run-debugger-vertical-layout:v1";
const HORIZONTAL_LAYOUT_STORAGE_KEY = "ergon-run-debugger-horizontal-layout:v1";
const DEFAULT_VERTICAL_LAYOUT: Layout = { "graph-workspace": 62, timeline: 38 };
const DEFAULT_HORIZONTAL_LAYOUT: Layout = { graph: 58, workspace: 42 };

function loadPanelLayout(storageKey: string, fallback: Layout): Layout {
  if (typeof window === "undefined") return fallback;

  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Layout;
    return Object.fromEntries(
      Object.entries(fallback).map(([id, defaultSize]) => {
        const size = parsed[id];
        return [id, Number.isFinite(size) ? size : defaultSize];
      }),
    );
  } catch {
    return fallback;
  }
}

function savePanelLayout(storageKey: string, layout: Layout): void {
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(layout));
  } catch {
    // Ignore storage failures; resizing should still work for the session.
  }
}

export function panelPercent(layout: Layout, id: string, fallback: number): string {
  const size = layout[id];
  return `${Number.isFinite(size) ? size : fallback}%`;
}

export function useRunPanelLayout() {
  const [verticalLayout, setVerticalLayoutState] = useState<Layout>(() =>
    loadPanelLayout(VERTICAL_LAYOUT_STORAGE_KEY, DEFAULT_VERTICAL_LAYOUT),
  );
  const [horizontalLayout, setHorizontalLayoutState] = useState<Layout>(() =>
    loadPanelLayout(HORIZONTAL_LAYOUT_STORAGE_KEY, DEFAULT_HORIZONTAL_LAYOUT),
  );
  const [hasLoadedPanelLayouts, setHasLoadedPanelLayouts] = useState(false);

  useEffect(() => {
    setVerticalLayoutState(loadPanelLayout(VERTICAL_LAYOUT_STORAGE_KEY, DEFAULT_VERTICAL_LAYOUT));
    setHorizontalLayoutState(
      loadPanelLayout(HORIZONTAL_LAYOUT_STORAGE_KEY, DEFAULT_HORIZONTAL_LAYOUT),
    );
    setHasLoadedPanelLayouts(true);
  }, []);

  const setVerticalLayout = (layout: Layout) => {
    setVerticalLayoutState(layout);
    savePanelLayout(VERTICAL_LAYOUT_STORAGE_KEY, layout);
  };

  const setHorizontalLayout = (layout: Layout) => {
    setHorizontalLayoutState(layout);
    savePanelLayout(HORIZONTAL_LAYOUT_STORAGE_KEY, layout);
  };

  return {
    verticalLayout,
    setVerticalLayout,
    horizontalLayout,
    setHorizontalLayout,
    hasLoadedPanelLayouts,
  };
}
