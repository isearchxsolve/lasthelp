import { describe, it, expect } from 'vitest';
import { resolveToken, flattenTokens } from './resolve';

describe('token resolution', () => {
  it('resolves a literal token', () => {
    expect(resolveToken({ value: '#ff0000' })).toBe('#ff0000');
  });

  it('resolves a reference token', () => {
    const tokens = {
      'color.red': { value: '#ff0000' },
      'color.brand': { value: '{color.red}' },
    };
    expect(resolveToken(tokens['color.brand'], tokens)).toBe('#ff0000');
  });

  it('flattens nested groups into dot paths', () => {
    const out = flattenTokens({
      color: { red: { value: '#ff0000' } },
      space: { md: { value: '16px' } },
    });
    expect(out['color.red'].value).toBe('#ff0000');
    expect(out['space.md'].value).toBe('16px');
  });
});
