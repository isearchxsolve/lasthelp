import { describe, it, expect } from 'vitest';
import { validateIR, normalizeIR, cloneNode } from './ops';
import type { IRDocument, IRNode } from './types';



// Deep clone
describe('deepClone', () => {
  it('clones a simple node', () => {
    const node: IRNode = {
      id: 'n1', type: 'Box', props: {},
      children: [{ id: 'n2', type: 'Text', props: { text: 'hi' }, children: [] }],
    };
    const cloned = cloneNode(node);
    expect(cloned).not.toBe(node);
    expect(cloned.children[0]).not.toBe(node.children[0]);
    expect(cloned.children[0].props.text).toBe('hi');
  });

  it('preserves nested structure', () => {
    const node: IRNode = {
      id: 'root', type: 'Box', props: {},
      children: [
        { id: 'c1', type: 'Text', props: { text: 'a' }, children: [] },
        {
          id: 'c2', type: 'Box', props: { border: 1 },
          children: [{ id: 'gc', type: 'Text', props: { text: 'b' }, children: [] }],
        },
      ],
    };
    const cloned = cloneNode(node);
    expect(cloned.id).toBe('root');
    expect(cloned.children).toHaveLength(2);
    expect(cloned.children[1].id).toBe('c2');
    expect(cloned.children[1].children[0].id).toBe('gc');
    expect(cloned.children[1].children[0].props.text).toBe('b');
  });

  it('does not share references', () => {
    const node: IRNode = {
      id: 'parent', type: 'Box', props: {},
      children: [{ id: 'child', type: 'Text', props: { text: 'shared' }, children: [] }],
    };
    const cloned = cloneNode(node);
    // Mutate clone
    cloned.children[0].props.text = 'not shared';
    // Original untouched
    expect(node.children[0].props.text).toBe('shared');
  });
});



// Validate IR
describe('validateIR', () => {
  it('accepts minimal valid document', () => {
    const doc: IRDocument = {
      id: 'doc', type: 'Root', version: 1, props: {},
      children: [{ id: 'n1', type: 'Box', props: {}, children: [] }],
    };
    const result = validateIR(doc);
    expect(result.ok).toBe(true);
    expect(result.errors).toHaveLength(0);
  });

  it('rejects duplicate ids', () => {
    const doc: IRDocument = {
      id: 'root', type: 'Root', version: 1, props: {},
      children: [
        { id: 'dup', type: 'Box', props: {}, children: [{ id: 'dup', type: 'Text', props: {}, children: [] }] },
      ],
    };
    const result = validateIR(doc);
    expect(result.ok).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].code).toBe('DUPLICATE_ID');
  });

  it('rejects missing required props', () => {
    const doc: IRDocument = {
      id: 'root', type: 'Root', version: 1, props: {},
      children: [{ id: 'img', type: 'Image', props: {}, children: [] }],
    };
    const result = validateIR(doc);
    expect(result.ok).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].code).toBe('MISSING_REQUIRED_PROP');
  });

  it('rejects unknown node type', () => {
    const doc: IRDocument = {
      id: 'root', type: 'Root', version: 1, props: {},
      children: [{ id: 'bad', type: 'UnknownType', props: {}, children: [] }],
    };
    const result = validateIR(doc);
    expect(result.ok).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].code).toBe('UNKNOWN_NODE_TYPE');
  });

  it('accepts nested valid structure', () => {
    const doc: IRDocument = {
      id: 'root', type: 'Root', version: 1, props: {},
      children: [
        { id: 'n1', type: 'Box', props: { padding: 8 }, children: [] },
        {
          id: 'n2', type: 'Text', props: { text: 'hello' }, children: [
            { id: 'n3', type: 'Box', props: { color: 'red' }, children: [] }
          ]
        },
      ],
    };
    const result = validateIR(doc);
    expect(result.ok).toBe(true);
    expect(result.errors).toHaveLength(0);
  });
});



// Normalize IR
describe('normalizeIR', () => {
  it('fills missing id with uuid', () => {
    const node: IRNode = {
      id: '', type: 'Box', props: {}, children: [] };
    const normalized = normalizeIR(node);
    expect(normalized.id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  });

  it('preserves existing id', () => {
    const node: IRNode = {
      id: 'keep-me', type: 'Box', props: {}, children: [] };
    const normalized = normalizeIR(node);
    expect(normalized.id).toBe('keep-me');
  });

  it('normalizes children recursively', () => {
    const node: IRNode = {
      id: 'parent', type: 'Box', props: {},
      children: [{ id: '', type: 'Text', props: { text: 'hi' }, children: [] }];
    });
    const normalized = normalizeIR(node);
    expect(normalized.id).toBe('parent');
    expect(normalized.children[0].id).not.toBe('');
    expect(normalized.children[0].id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  });

  it('leaves other props untouched', () => {
    const node: IRNode = {
      id: 'n1', type: 'Box', props: { opacity: 0.5, hidden: true }, children: [] };
    const normalized = normalizeIR(node);
    expect(normalized.props.opacity).toBe(0.5);
    expect(normalized.props.hidden).toBe(true);
  });
});



// Export
export { validateIR, normalizeIR, cloneNode };