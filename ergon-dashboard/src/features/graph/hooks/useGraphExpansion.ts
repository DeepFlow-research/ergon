import { createContext, useContext } from "react";

interface GraphExpansionState {
  expandedContainers: Set<string>;
  toggleExpand: (taskId: string) => void;
  containerDimensions: Map<string, { width: number; height: number }>;
}

const GraphExpansionContext = createContext<GraphExpansionState>({
  expandedContainers: new Set(),
  toggleExpand: () => {},
  containerDimensions: new Map(),
});

export const GraphExpansionProvider = GraphExpansionContext.Provider;

export function useGraphExpansion(): GraphExpansionState {
  return useContext(GraphExpansionContext);
}
