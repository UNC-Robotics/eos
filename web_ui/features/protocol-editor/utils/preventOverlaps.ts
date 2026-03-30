import type { Node } from '@xyflow/react';

const GAP = 40; // Minimum gap between nodes

interface Rect {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w + GAP && a.x + a.w + GAP > b.x && a.y < b.y + b.h + GAP && a.y + a.h + GAP > b.y;
}

/**
 * Resolve overlapping React Flow nodes using their actual measured dimensions.
 * Processes nodes left-to-right, pushing each node clear of all previously placed nodes.
 *
 * Returns new node array with updated positions, or null if no overlaps were found.
 */
export function resolveOverlaps<T extends Record<string, unknown>>(nodes: Node<T>[]): Node<T>[] | null {
  if (nodes.length < 2) return null;

  // Build rects from measured dimensions — skip if any node hasn't been measured yet
  const rects: Rect[] = [];
  for (const node of nodes) {
    const w = node.measured?.width ?? node.width;
    const h = node.measured?.height ?? node.height;
    if (!w || !h) return null; // Not all measured yet
    rects.push({ id: node.id, x: node.position.x, y: node.position.y, w, h });
  }

  // Check if there are any overlaps at all
  let hasOverlap = false;
  for (let i = 0; i < rects.length && !hasOverlap; i++) {
    for (let j = i + 1; j < rects.length && !hasOverlap; j++) {
      if (rectsOverlap(rects[i], rects[j])) hasOverlap = true;
    }
  }
  if (!hasOverlap) return null;

  // Sort left-to-right, top-to-bottom
  rects.sort((a, b) => a.x - b.x || a.y - b.y);

  // For each node, push it clear of all previously placed nodes
  for (let i = 1; i < rects.length; i++) {
    const current = rects[i];

    for (let attempt = 0; attempt < 50; attempt++) {
      let worstBlocker: Rect | null = null;
      let worstArea = 0;

      for (let j = 0; j < i; j++) {
        if (!rectsOverlap(current, rects[j])) continue;

        const penX =
          Math.min(rects[j].x + rects[j].w + GAP, current.x + current.w + GAP) - Math.max(rects[j].x, current.x);
        const penY =
          Math.min(rects[j].y + rects[j].h + GAP, current.y + current.h + GAP) - Math.max(rects[j].y, current.y);

        const area = penX * penY;
        if (area > worstArea) {
          worstArea = area;
          worstBlocker = rects[j];
        }
      }

      if (!worstBlocker) break;

      const penX =
        Math.min(worstBlocker.x + worstBlocker.w + GAP, current.x + current.w + GAP) -
        Math.max(worstBlocker.x, current.x);
      const penY =
        Math.min(worstBlocker.y + worstBlocker.h + GAP, current.y + current.h + GAP) -
        Math.max(worstBlocker.y, current.y);

      if (penX <= penY) {
        if (current.x >= worstBlocker.x) {
          current.x = worstBlocker.x + worstBlocker.w + GAP;
        } else {
          current.x = worstBlocker.x - current.w - GAP;
        }
      } else {
        if (current.y >= worstBlocker.y) {
          current.y = worstBlocker.y + worstBlocker.h + GAP;
        } else {
          current.y = worstBlocker.y - current.h - GAP;
        }
      }
    }
  }

  // Build position map
  const posMap = new Map(rects.map((r) => [r.id, { x: Math.round(r.x), y: Math.round(r.y) }]));

  return nodes.map((node) => ({
    ...node,
    position: posMap.get(node.id) ?? node.position,
  }));
}
