export interface TokenNode { value: string; type?: string; }
export type TokenGroup = { [k: string]: TokenNode | TokenGroup };
export type FlatTokens = Record<string, TokenNode>;

const REF = /\{([^}]+)\}/g;

/** Flatten a nested token tree into dot-pathed keys. */
export function flattenTokens(group: TokenGroup, prefix = ''): FlatTokens {
  const out: FlatTokens = {};
  for (const [k, v] of Object.entries(group)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if ('value' in v) out[path] = v as TokenNode;
    else Object.assign(out, flattenTokens(v as TokenGroup, path));
  }
  return out;
}

/** Resolve a token, following {a.b} references. */
export function resolveToken(node: TokenNode, all?: FlatTokens, seen = new Set<string>()): string {
  const m = node.value.match(REF);
  if (!m) return node.value;
  let result = node.value;
  for (const ref of m) {
    const key = ref.slice(1, -1);
    if (seen.has(key)) throw new Error(`circular token ref: ${key}`);
    if (!all?.[key]) throw new Error(`unresolved token ref: ${key}`);
    const resolved = resolveToken(all[key], all, new Set([...seen, key]));
    result = result.replace(ref, resolved);
  }
  return result;
}
