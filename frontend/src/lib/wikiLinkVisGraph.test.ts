import { describe, expect, it } from 'vitest'
import { graphNodeDiameter, graphNodeVisRadius } from './graphNodeSymbolSize'
import { buildVisWikiGraph, DEFAULT_WIKI_GRAPH_SIZING, wikiLinkNetworkOptions } from './wikiLinkVisGraph'

describe('graphNodeSymbolSize', () => {
  it('matches tag graph diameter formula and vis radius is half', () => {
    expect(graphNodeDiameter(3, 48, 1)).toBe(144)
    expect(graphNodeVisRadius(3, 48, 1)).toBe(72)
    expect(graphNodeDiameter(0, 48, 1)).toBe(48)
  })
})

describe('buildVisWikiGraph', () => {
  it('maps API nodes/edges to vis datasets with hub diamond shape', () => {
    const data = {
      nodes: [
        { id: 1, name: 'Doc A', value: 3, page_kind: 'source', wiki_slug: null },
        { id: 2, name: 'Topic X', value: 2, page_kind: 'concept', wiki_slug: 'topic-x' },
      ],
      links: [
        { source: 1, target: 2, value: 1, edge_type: 'wiki_topic' as const, wiki_slug: 'topic-x' },
      ],
      truncated: false,
      total_files_with_links: 2,
    }
    const { visNodes, visEdges, nodeMeta } = buildVisWikiGraph(data, true, '#2997ff')
    expect(visNodes).toHaveLength(2)
    expect(visNodes[0].shape).toBe('dot')
    expect(visNodes[1].shape).toBe('diamond')
    expect(visEdges[0].from).toBe('1')
    expect(visEdges[0].to).toBe('2')
    expect(nodeMeta.get('2')?.isHub).toBe(true)
  })

  it('uses system sizing for node radius and edge width', () => {
    const data = {
      nodes: [{ id: 1, name: 'Doc', value: 2, page_kind: 'source', wiki_slug: null }],
      links: [{ source: 1, target: 1, value: 1, edge_type: 'file_direct' as const, wiki_slug: null }],
      truncated: false,
      total_files_with_links: 1,
    }
    const { visNodes, visEdges } = buildVisWikiGraph(data, true, '#2997ff', {
      singleBase: 40,
      displayRatio: 1,
      edgeLineWidth: 3,
    })
    expect(visNodes[0].size).toBe(graphNodeVisRadius(2, 40, 1))
    expect(visEdges[0].width).toBe(3)
    expect(buildVisWikiGraph(data, true, '#2997ff').visNodes[0].size).toBe(
      graphNodeVisRadius(2, DEFAULT_WIKI_GRAPH_SIZING.singleBase, DEFAULT_WIKI_GRAPH_SIZING.displayRatio),
    )
  })

  it('uses forceAtlas2Based physics like graphify html', () => {
    const opts = wikiLinkNetworkOptions()
    expect(opts.physics?.solver).toBe('forceAtlas2Based')
    expect(opts.physics?.stabilization?.iterations).toBe(200)
  })
})
