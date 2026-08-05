/**
 * Interaction model tests (Vitest). Pure functions — no DOM needed.
 * See DESIGN.md §5. Red phase: fail until modules exist.
 */
import { describe, it, expect } from 'vitest';
import { applySelection, marqueeSelect } from './selection';
import { snapMove, snapToGrid, SNAP_TOLERANCE } from './snapping';
import { matchShortcut, eventToCombo, DEFAULT_SHORTCUTS } from './shortcuts';

describe('selection', () => {
  it('set replaces selection', () => {
    const s = applySelection(new Set(['a']), { type: 'set', ids: ['b', 'c'] });
    expect([...s]).toEqual(['b', 'c']);
  });
  it('toggle adds/removes', () => {
    const s = applySelection(new Set(['a', 'b']), { type: 'toggle', ids: ['b', 'd'] });
    expect([...s].sort()).toEqual(['a', 'd']);
  });
  it('clear empties', () => {
    expect(applySelection(new Set(['a']), { type: 'clear' }).size).toBe(0);
  });
  it('marquee intersect selects overlapping', () => {
    const nodes = [{ id: 'n1', x: 0, y: 0, w: 10, h: 10 }, { id: 'n2', x: 100, y: 100, w: 10, h: 10 }];
    const res = marqueeSelect(nodes, { x: 5, y: 5, w: 20, h: 20 }, 'intersect');
    expect(res).toEqual(['n1']);
  });
  it('marquee contain requires full enclosure', () => {
    const nodes = [{ id: 'n1', x: 0, y: 0, w: 10, h: 10 }];
    const res = marqueeSelect(nodes, { x: 5, y: 5, w: 20, h: 20 }, 'contain');
    expect(res).toEqual([]);
  });
});

describe('snapping', () => {
  it('snaps to grid when no object nearby', () => {
    const r = snapMove({ x: 7, y: 7, w: 10, h: 10 }, 3, 3, []);
    expect(r.x % 8).toBe(0);
    expect(r.y % 8).toBe(0);
  });
  it('snaps to sibling edge within tolerance', () => {
    const others = [{ x: 100, y: 100, w: 50, h: 50 }];
    const r = snapMove({ x: 0, y: 0, w: 40, h: 40 }, 97, 0, others); // right edge at 137, sibling left at 100
    // left edge of moving at 97; sibling left 100 -> within tol -> snap to 100
    expect(r.x).toBe(100);
    expect(r.guides.length).toBeGreaterThan(0);
  });
  it('snapToGrid rounds to nearest multiple', () => {
    expect(snapToGrid(7, 8)).toBe(8);
    expect(snapToGrid(4, 8)).toBe(0);
  });
  it('tolerance is 6px', () => {
    expect(SNAP_TOLERANCE).toBe(6);
  });
});

describe('shortcuts', () => {
  it('eventToCombo normalizes a Cmd+K event', () => {
    const e = new KeyboardEvent('keydown', { key: 'k', metaKey: true });
    expect(eventToCombo(e)).toBe('Mod+K');
  });
  it('matchShortcut finds the palette open binding', () => {
    const e = new KeyboardEvent('keydown', { key: 'k', metaKey: true });
    const hit = matchShortcut(e, 'global');
    expect(hit?.action).toBe('palette.open');
  });
  it('DEFAULT_SHORTCUTS includes undo and redo', () => {
    expect(DEFAULT_SHORTCUTS.some((s) => s.action === 'edit.undo')).toBe(true);
    expect(DEFAULT_SHORTCUTS.some((s) => s.action === 'edit.redo')).toBe(true);
  });
});
