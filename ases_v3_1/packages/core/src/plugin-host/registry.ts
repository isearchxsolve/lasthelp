import type { Plugin, PluginManifest, PluginKind } from './types';

/** Plugin host registry. Versioned, kind-scoped. See ARCHITECTURE.md §3. */
export class PluginRegistry {
  private byKind = new Map<PluginKind, Map<string, Plugin>>();
  private manifests = new Map<string, PluginManifest>();

  register(plugin: Plugin): void {
    const m = plugin.manifest;
    if (this.manifests.has(m.id)) {
      throw new Error(`plugin already registered: ${m.id}`);
    }
    let bucket = this.byKind.get(m.kind);
    if (!bucket) { bucket = new Map(); this.byKind.set(m.kind, bucket); }
    bucket.set(m.id, plugin);
    this.manifests.set(m.id, m);
  }

  unregister(id: string): void {
    const m = this.manifests.get(id);
    if (!m) return;
    this.byKind.get(m.kind)?.delete(id);
    this.manifests.delete(id);
  }

  get(kind: PluginKind, id: string): Plugin | undefined {
    return this.byKind.get(kind)?.get(id);
  }

  list(kind: PluginKind): Plugin[] {
    return Array.from(this.byKind.get(kind)?.values() ?? []);
  }

  has(id: string): boolean { return this.manifests.has(id); }

  size(): number { return this.manifests.size; }
}
