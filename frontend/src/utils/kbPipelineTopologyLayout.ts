import type { PipelineTopologyEdge, PipelineTopologyNode } from '@/api/admin'

/** Assign nodes to layers from directed edges (longest path from sources). */
export function groupNodesByLayer(
  nodes: PipelineTopologyNode[],
  edges: PipelineTopologyEdge[],
): PipelineTopologyNode[][] {
  if (nodes.length === 0) return []

  const layer = new Map<string, number>()
  for (const node of nodes) {
    layer.set(node.id, 0)
  }

  for (let pass = 0; pass < nodes.length; pass += 1) {
    for (const edge of edges) {
      const next = (layer.get(edge.source) ?? 0) + 1
      layer.set(edge.target, Math.max(layer.get(edge.target) ?? 0, next))
    }
  }

  const order = new Map(nodes.map((node, index) => [node.id, index]))
  const maxLayer = Math.max(0, ...layer.values())
  const groups: PipelineTopologyNode[][] = Array.from({ length: maxLayer + 1 }, () => [])

  for (const node of nodes) {
    groups[layer.get(node.id) ?? 0].push(node)
  }

  for (const group of groups) {
    group.sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0))
  }

  return groups.filter((group) => group.length > 0)
}

export function hasMineruToDoclingEdge(edges: PipelineTopologyEdge[]): boolean {
  return edges.some((edge) => edge.source === 'mineru' && edge.target === 'docling')
}

export function areMineruDoclingParallel(
  nodes: PipelineTopologyNode[],
  edges: PipelineTopologyEdge[],
): boolean {
  const layers = groupNodesByLayer(nodes, edges)
  const layerIndex = (id: string) => layers.findIndex((layer) => layer.some((node) => node.id === id))
  const mineruLayer = layerIndex('mineru')
  const doclingLayer = layerIndex('docling')
  if (mineruLayer < 0 || doclingLayer < 0) return true
  return mineruLayer === doclingLayer
}

/** Sample topology matching backend `kb_pipeline_topology_service`. */
export function samplePipelineTopology(): {
  nodes: PipelineTopologyNode[]
  edges: PipelineTopologyEdge[]
} {
  const nodes: PipelineTopologyNode[] = [
    { id: 'upload', label: 'upload', kind: 'stage', highlight: false },
    { id: 'extract_enqueue', label: 'enqueue', kind: 'queue', highlight: false },
    { id: 'kb_extract', label: 'kb-extract', kind: 'worker', highlight: true },
    { id: 'mineru', label: 'mineru', kind: 'sidecar', highlight: true },
    { id: 'docling', label: 'docling', kind: 'sidecar', highlight: true },
    { id: 'md_notes', label: 'md_notes', kind: 'artifact', highlight: false },
  ]
  const edges: PipelineTopologyEdge[] = [
    { source: 'upload', target: 'extract_enqueue' },
    { source: 'extract_enqueue', target: 'kb_extract' },
    { source: 'kb_extract', target: 'mineru' },
    { source: 'kb_extract', target: 'docling' },
    { source: 'kb_extract', target: 'md_notes' },
    { source: 'mineru', target: 'md_notes' },
    { source: 'docling', target: 'md_notes' },
  ]
  return { nodes, edges }
}
