import { describe, expect, it } from 'vitest'
import { buildDisplayTopology } from '@/utils/agentRunTopology'
import {
  computeEdgePolyline,
  polylineIntersectsObstacles,
  type FlowEdgeObstacle,
} from '@/utils/agentRunFlowEdges'
import {
  computeKbFullPlacements,
  FLOW_NODE_HEIGHT,
  FLOW_NODE_WIDTH,
  FLOW_WIDE_NODE_HEIGHT,
  FLOW_WIDE_NODE_WIDTH,
  type FlowNodePlacement,
} from '@/utils/agentRunFlowLayout'

function node(
  partial: Partial<FlowNodePlacement> & Pick<FlowNodePlacement, 'left' | 'top' | 'lane'>,
): FlowNodePlacement {
  return {
    width: partial.width ?? FLOW_NODE_WIDTH,
    height: partial.height ?? FLOW_NODE_HEIGHT,
    ...partial,
  }
}

describe('agentRunFlowEdges', () => {
  it('uses a straight horizontal segment on the same row', () => {
    const source = node({ left: 90, top: 82, lane: 'L1' })
    const target = node({ left: 292, top: 82, lane: 'L1' })
    expect(computeEdgePolyline(source, target)).toBe('M 236 130 L 292 130')
  })

  it('uses orthogonal polyline instead of curves for row changes', () => {
    const source = node({ left: 636, top: 280, lane: 'L2' })
    const target = node({ left: 1000, top: 420, lane: 'L2' })
    const path = computeEdgePolyline(source, target)
    expect(path).not.toContain('C ')
    expect(path).toContain('L ')
    expect(path.startsWith('M 782 328')).toBe(true)
  })

  it('routes L1 to L2 through the gutter with sharp corners', () => {
    const source = node({ left: 494, top: 82, lane: 'L1' })
    const target = node({ left: 90, top: 280, lane: 'L2' })
    const path = computeEdgePolyline(source, target)
    expect(path).not.toContain('C ')
    expect(path).toContain('L 666 130')
    expect(path).toContain('L 666 202')
    expect(path).toContain('L 64 202')
  })

  it('draws a vertical polyline for stacked tail nodes', () => {
    const source = node({ left: 1000, top: 420, lane: 'L2' })
    const target = node({ left: 1000, top: 560, lane: 'L2' })
    expect(computeEdgePolyline(source, target)).toBe('M 1073 516 L 1073 560')
  })

  it('routes assess to worker below without crossing the worker box horizontally', () => {
    const assess = node({ left: 636, top: 280, lane: 'L2' })
    const worker = node({
      left: 636,
      top: 280 + FLOW_NODE_HEIGHT + 40,
      lane: 'L2',
      width: FLOW_WIDE_NODE_WIDTH,
      height: FLOW_WIDE_NODE_HEIGHT,
      wide: true,
    })
    const path = computeEdgePolyline(assess, worker)
    expect(path).toContain('376')
    expect(path).not.toMatch(/328 L \d+ 328 L 818/)
  })

  it('keeps assess-to-wiki horizontal segments out of the worker obstacle', () => {
    const events = [
      {
        seq: 1,
        layer: 'kb' as const,
        node_id: 'get_md_worker',
        phase: 'end' as const,
        attempt: 1,
        ts: '2026-07-03T00:00:00+08:00',
        label: '补读文档',
        task_key: 'get_md:file_id=350',
      },
    ]
    const { nodes } = buildDisplayTopology(events, 'kb_full')
    const placements = computeKbFullPlacements(nodes)
    const obstacles: FlowEdgeObstacle[] = nodes.map((item) => ({
      id: item.id,
      placement: placements.get(item.id)!,
    }))
    const assess = nodes.find((item) => item.templateId === 'assess')!
    const wiki = nodes.find((item) => item.templateId === 'wiki_expand')!
    const worker = nodes.find((item) => item.templateId === 'get_md_worker')!

    const path = computeEdgePolyline(
      placements.get(assess.id)!,
      placements.get(wiki.id)!,
      { sourceId: assess.id, targetId: wiki.id, obstacles },
    )

    expect(
      polylineIntersectsObstacles(path, obstacles, [assess.id, wiki.id, worker!.id]),
    ).toBe(false)
  })
})
