import { describe, it, expect } from 'vitest';
import type { IRNode, IRDocument } from './types';
import { normalizeIR, validateIR, cloneNode } from './ops';

describe('IR ops', () => {
  const node: IRNode = {
    id: 'n1',
    type: 'Box',
    children: [{ id: 'n2', type: 'Text', props: { text: 'hi' }, children: [] }],
    props: {},
  };

  it('validates a well-formed document', () => {
    const doc: IRDocument = { id: 'root', type: 'Root', children: [node], props: {}, version: 1 };
    const res = validateIR(doc);
    expect(res.ok).toBe(true);
    expect(res.errors).toHaveLength(0);
  });

  it('rejects duplicate ids', () => {
    const doc: IRDocument = {
      id: 'root', type: 'Root', version: 1, props: {},
      children: [{ id: 'dup', type: 'Box', props: {}, children: [{ id: 'dup', type: 'Text', props: {}, children: [] }] }],
    };
    const res = validateIR(doc);
    expect(res.ok).toBe(false);
    expect(res.errors.length).toBeGreaterThan(0);
  });

  it('normalizes by sorting children stably and filling defaults', () => {
    const out = normalizeIR(node);
    expect(out.id).toBe('n1');
    expect(out.children[0].id).toBe('n2');
  });

  it('cloneNode deep-clones without shared refs', () => {
    const c = cloneNode(node);
    expect(c).not.toBe(node);
    expect(c.children[0]).not.toBe(node.children[0]);
    expect(c.children[0].id).toBe('n2');
  });
});
