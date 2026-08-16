import { describe, expect, it } from 'vitest'
import {
  areMineruDoclingParallel,
  groupNodesByLayer,
  hasMineruToDoclingEdge,
  samplePipelineTopology,
} from './kbPipelineTopologyLayout'

describe('kbPipelineTopologyLayout', () => {
  it('does not treat mineru and docling as a serial edge', () => {
    const { edges } = samplePipelineTopology()
    expect(hasMineruToDoclingEdge(edges)).toBe(false)
  })

  it('places mineru and docling in the same parallel layer after kb_extract', () => {
    const { nodes, edges } = samplePipelineTopology()
    expect(areMineruDoclingParallel(nodes, edges)).toBe(true)

    const layers = groupNodesByLayer(nodes, edges)
    const layerOf = (id: string) => layers.findIndex((layer) => layer.some((node) => node.id === id))

    expect(layerOf('kb_extract')).toBeLessThan(layerOf('mineru'))
    expect(layerOf('mineru')).toBe(layerOf('docling'))
    expect(layerOf('md_notes')).toBeGreaterThan(layerOf('mineru'))
  })
})
