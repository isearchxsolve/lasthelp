// ASES v3.1 — Selection & Multi-Select
// See DESIGN.md §5.1. Interface stubs only — no feature logic.

export type SelectionMode = 'single' | 'add' | 'toggle' | 'marquee';

export interface SelectionState {
  selectedIds: string[];
  primaryId: string | null;
}

export interface SelectionController {
  state(): SelectionState;
  select(id: string, mode?: SelectionMode): void;
  clear(): void;
  marquee(rect: { x: number; y: number; w: number; h: number }, containedOnly: boolean): void;
  subscribe(listener: (s: SelectionState) => void): () => void;
}
