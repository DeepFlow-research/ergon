/**
 * Depth-based accent colours (Fractal-style progression: cool → warm).
 * Used for graph headers, borders, and edge tints — not semantic task status.
 */

type RGB = readonly [number, number, number];

/** Anchor stops: blue → emerald → amber → orange → magenta-red */
const ANCHORS: readonly RGB[] = [
  [42, 170, 236],
  [46, 204, 113],
  [255, 196, 0],
  [255, 106, 43],
  [234, 25, 93],
];

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

function rgbToHex(r: number, g: number, b: number): string {
  const to = (x: number) => clamp(x, 0, 255).toString(16).padStart(2, "0");
  return `#${to(r)}${to(g)}${to(b)}`;
}

/**
 * Returns a hex colour for the given tree level (0 = root).
 * When maxDepth is 0, treats as single-level graph.
 */
export function getLevelColor(level: number, maxDepth: number): string {
  const denom = Math.max(1, maxDepth);
  const t = clamp(level / denom, 0, 1);
  const scaled = t * (ANCHORS.length - 1);
  const i = Math.floor(scaled);
  const f = scaled - i;
  if (i >= ANCHORS.length - 1) {
    const [r, g, b] = ANCHORS[ANCHORS.length - 1];
    return rgbToHex(r, g, b);
  }
  const a = ANCHORS[i];
  const b = ANCHORS[i + 1];
  return rgbToHex(lerp(a[0], b[0], f), lerp(a[1], b[1], f), lerp(a[2], b[2], f));
}
