import type { IRNode, IRDocument } from './types';

export interface ValidationResult { ok: boolean; errors: string[]; }

/** Validate IR document: unique ids, non-empty root, version present. */
export function validateIR(doc: IRDocument): ValidationResult {
  const errors: string[] = [];
  const seen = new Set<string>();
  const walk = (n: IRNode): void => {
    if (!n.id) errors.push('node missing id');
    else if (seen.has(n.id)) errors.push(`duplicate id: ${n.id}`);
    else seen.add(n.id);
    if (!n.type) errors.push(`node ${n.id ?? '?'} missing type`);
    for (const c of n.children ?? []) walk(c);
  };
  if (!doc.version) errors.push('document missing version');
  walk(doc);
  return { ok: errors.length === 0, errors };
}

/** Normalize: ensure children arrays exist, props defined, deterministic order. */
export function normalizeIR(node: IRNode): IRNode {
  const out: IRNode = {
    id: node.id,
    type: node.type,
    props: node.props ?? {},
    children: (node.children ?? []).map(normalizeIR),
  };
  return out;
}

/** Deep clone a node (no shared refs). */
export function cloneNode(node: IRNode): IRNode {
  return {
    id: node.id,
    type: node.type,
    props: node.props ? structuredCloneSafe(node.props) : {},
    children: (node.children ?? []).map(cloneNode),
  };
}

function structuredCloneSafe<T>(v: T): T {
  return JSON.parse(JSON.stringify(v));
}
