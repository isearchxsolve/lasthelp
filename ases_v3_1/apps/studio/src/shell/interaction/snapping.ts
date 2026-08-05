/**
 * Smart snapping + alignment guides. See DESIGN.md §5.2.
 * Snapping tolerance 6px. Guides fade after 400ms idle.
 * Pure geometry helpers — no DOM, no PixiJS. Tested in isolation.
 */
export interface Rect { x: number; y: number; w: number; h: number }
export interface Guide { axis: 'x' | 'y'; pos: number; from: number; to: number }

export const SNAP_TOLERANCE = 6; // px
export const GRID_SIZE = 8; // px default snap grid

export interface SnapResult {
  x: number;
  y: number;
  guides: Guide[];
}

/**
 * Snap a moving rect against a set of other rects' edges + centers.
 * Returns the adjusted origin and the guides that triggered.
 */
export function snapMove(
  moving: Rect,
  dx: number,
  dy: number,
  others: Rect[],
  tol: number = SNAP_TOLERANCE,
): SnapResult {
  const guides: Guide[] = [];
  let snapX: number | null = null;
  let snapY: number | null = null;

  const movingEdges = {
    left: moving.x + dx,
    cx: moving.x + dx + moving.w / 2,
    right: moving.x + dx + moving.w,
  };
  const movingEdgesY = {
    top: moving.y + dy,
    cy: moving.y + dy + moving.h / 2,
    bottom: moving.y + dy + moving.h,
  };

  for (const o of others) {
    const ox = { left: o.x, cx: o.x + o.w / 2, right: o.x + o.w };
    for (const [mName, mVal] of Object.entries(movingEdges)) {
      for (const [oName, oVal] of Object.entries(ox)) {
        if (Math.abs(mVal - oVal) <= tol) {
          snapX = oVal - (mName === 'left' ? 0 : mName === 'cx' ? moving.w / 2 : moving.w);
          guides.push({ axis: 'x', pos: oVal, from: Math.min(moving.y + dy, o.y), to: Math.max(moving.y + dy + moving.h, o.y + o.h) });
        }
      }
    }
    const oy = { top: o.y, cy: o.y + o.h / 2, bottom: o.y + o.h };
    for (const [mName, mVal] of Object.entries(movingEdgesY)) {
      for (const [oName, oVal] of Object.entries(oy)) {
        if (Math.abs(mVal - oVal) <= tol) {
          snapY = oVal - (mName === 'top' ? 0 : mName === 'cy' ? moving.h / 2 : moving.h);
          guides.push({ axis: 'y', pos: oVal, from: Math.min(moving.x + dx, o.x), to: Math.max(moving.x + dx + moving.w, o.x + o.w) });
        }
      }
    }
  }

  // Grid snap fallback when no object snap
  if (snapX === null) snapX = snapToGrid(moving.x + dx, GRID_SIZE);
  if (snapY === null) snapY = snapToGrid(moving.y + dy, GRID_SIZE);

  return { x: snapX, y: snapY, guides };
}

export function snapToGrid(v: number, grid: number = GRID_SIZE): number {
  return Math.round(v / grid) * grid;
}

/** SnappingEngine interface stub — see DESIGN.md §5.2. */
export interface SnappingEngine {
  tolerance: number;
  snap(moving: Rect, targets: Rect[]): SnapResult;
}