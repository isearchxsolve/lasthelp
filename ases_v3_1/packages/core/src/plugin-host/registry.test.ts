import { describe, it, expect } from 'vitest';
import { PluginRegistry } from './registry';
import type { Plugin, PluginManifest } from './types';

const manifest = (id: string, kind: any): PluginManifest => ({
  id, kind, name: id, version: '1.0.0', apiVersion: 1,
});

const plugin = (id: string, kind: any): Plugin => ({
  manifest: manifest(id, kind),
  activate: () => {},
  deactivate: () => {},
});

describe('PluginRegistry', () => {
  it('registers and retrieves by kind', () => {
    const r = new PluginRegistry();
    r.register(plugin('react', 'codegen'));
    expect(r.get('codegen', 'react')?.manifest.id).toBe('react');
    expect(r.list('codegen')).toHaveLength(1);
  });

  it('rejects duplicate registration', () => {
    const r = new PluginRegistry();
    r.register(plugin('react', 'codegen'));
    expect(() => r.register(plugin('react', 'codegen'))).toThrow();
  });

  it('unregisters', () => {
    const r = new PluginRegistry();
    r.register(plugin('react', 'codegen'));
    r.unregister('react');
    expect(r.has('react')).toBe(false);
    expect(r.size()).toBe(0);
  });
});
