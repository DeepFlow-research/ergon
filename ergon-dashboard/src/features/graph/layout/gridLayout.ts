/**
 * Grid placement for many sibling nodes with few inter-sibling dependency edges.
 */

export const GRID_GAP_X = 50;
export const GRID_GAP_Y = 50;

function calculateOptimalColumns(nodeCount: number): number {
  let columns = 5;
  let rows = Math.ceil(nodeCount / columns);
  while (rows > columns && columns < 20) {
    columns += 1;
    rows = Math.ceil(nodeCount / columns);
  }
  return columns;
}

/**
 * Lay out node ids in a rough square grid starting at (startX, startY).
 */
export function layoutNodesInGrid(
  nodeIds: string[],
  sizes: Map<string, { width: number; height: number }>,
  startX: number,
  startY: number,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  if (nodeIds.length === 0) return positions;

  const columns = calculateOptimalColumns(nodeIds.length);

  nodeIds.forEach((id, index) => {
    const row = Math.floor(index / columns);
    const col = index % columns;
    const size = sizes.get(id) ?? { width: 180, height: 90 };
    const x = startX + col * (size.width + GRID_GAP_X);
    const y = startY + row * (size.height + GRID_GAP_Y);
    positions.set(id, { x, y });
  });

  return positions;
}

/** Use grid when many siblings and almost no internal dependency edges. */
export function shouldLayoutChildrenAsGrid(
  childCount: number,
  internalEdgeCount: number,
): boolean {
  return childCount >= 6 && internalEdgeCount <= 1;
}
