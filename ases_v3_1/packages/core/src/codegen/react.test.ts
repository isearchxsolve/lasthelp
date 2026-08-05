import { describe, it, expect } from 'vitest';
import { generateReact, generateReactDocument } from './react';
import type { IRNode, IRDocument } from '../ir/types';

describe('React codegen', () => {
  it('renders a leaf Box as self-closing div', () => {
    const n: IRNode = { id: 'a', type: 'Box', props: {}, children: [] };
    expect(generateReact(n)).toBe('<div></div>');
  });

  it('renders Text as span with text prop', () => {
    const n: IRNode = { id: 'a', type: 'Text', props: { text: 'hi' }, children: [] };
    expect(generateReact(n)).toBe('<span text="hi"></span>');
  });

  it('renders nested children with indentation', () => {
    const n: IRNode = {
      id: 'a', type: 'Box', props: {},
      children: [{ id: 'b', type: 'Box', props: {}, children: [] }],
    };
    const out = generateReact(n);
    expect(out).toContain('<div>');
    expect(out).toContain('  <div></div>');
  });

  it('generateReactDocument joins top-level children', () => {
    const doc: IRDocument = {
      id: 'r', type: 'Root', version: 1, props: {},
      children: [{ id: 'a', type: 'Box', props: {}, children: [] }],
    };
    expect(generateReactDocument(doc)).toBe('<div></div>');
  });
});
