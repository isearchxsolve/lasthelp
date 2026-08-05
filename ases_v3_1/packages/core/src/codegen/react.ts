import type { IRNode, IRDocument } from '../ir/types';

/** React codegen target. Pure function of IR. See ARCHITECTURE.md §4. */
export function generateReact(node: IRNode, indent = 0): string {
  const pad = '  '.repeat(indent);
  const tag = node.type === 'Text' ? 'span' : node.type === 'Box' ? 'div' : node.type;
  const children = (node.children ?? []).map(c => generateReact(c, indent + 1)).join('\n');
  const props = formatProps(node.props);
  const open = props ? `<${tag} ${props}>` : `<${tag}>`;
  const close = `</${tag}>`;
  if (!children) return `${pad}${open}${close}`;
  return `${pad}${open}\n${children}\n${pad}${close}`;
}

function formatProps(props: Record<string, unknown> | undefined): string {
  if (!props || Object.keys(props).length === 0) return '';
  return Object.entries(props)
    .map(([k, v]) => `${k}=${JSON.stringify(String(v))}`)
    .join(' ');
}

export function generateReactDocument(doc: IRDocument): string {
  return doc.children.map(c => generateReact(c, 0)).join('\n');
}
