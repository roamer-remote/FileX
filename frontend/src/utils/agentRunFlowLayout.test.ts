import { describe, expect, it } from 'vitest'
import { buildDisplayTopology } from '@/utils/agentRunTopology'
import {
  computeCanvasBounds,
  computeKbFullPlacements,
  FLOW_CANVAS_PADDING,
  FLOW_NODE_HEIGHT,
  FLOW_NODE_WIDTH,
  FLOW_WIDE_NODE_WIDTH,
} from '@/utils/agentRunFlowLayout'

describe('agentRunFlowLayout', () => {
  it('places kb tail nodes after worker without clipping past fixed canvas width', () => {
    const events = [
      {
        seq: 1,
        layer: 'router' as const,
        node_id: 'classify',
        phase: 'end' as const,
        attempt: 1,
        ts: '2026-07-03T00:00:00+08:00',
        label: '理解意图',
      },
      {
        seq: 2,
        layer: 'kb' as const,
        node_id: 'get_md_worker',
        phase: 'end' as const,
        attempt: 1,
        ts: '2026-07-03T00:00:01+08:00',
        label: '补读文档',
        task_key: 'get_md:file_id=350',
      },
    ]
    const { nodes } = buildDisplayTopology(events, 'kb_full')
    const placements = computeKbFullPlacements(nodes)
    const verify = nodes.find((node) => node.templateId === 'verify_evidence')
    const synthesize = nodes.find((node) => node.templateId === 'synthesize')
    const worker = nodes.find((node) => node.templateId === 'get_md_worker')

    expect(worker).toBeTruthy()
    expect(verify).toBeTruthy()
    expect(synthesize).toBeTruthy()

    const workerPlacement = placements.get(worker!.id)!
    const verifyPlacement = placements.get(verify!.id)!
    const synthPlacement = placements.get(synthesize!.id)!

    expect(verifyPlacement.left).toBeGreaterThan(workerPlacement.left + FLOW_WIDE_NODE_WIDTH)
    expect(synthPlacement.left).toBe(verifyPlacement.left)
    expect(synthPlacement.top).toBeGreaterThan(verifyPlacement.top)

    const bounds = computeCanvasBounds(placements.values())
    expect(bounds.width).toBeGreaterThanOrEqual(
      verifyPlacement.left + FLOW_NODE_WIDTH + FLOW_CANVAS_PADDING,
    )
  })

  it('expands canvas width for parallel get_md workers', () => {
    const events = [
      {
        seq: 1,
        layer: 'kb' as const,
        node_id: 'get_md_worker',
        phase: 'start' as const,
        attempt: 1,
        ts: '2026-07-03T00:00:00+08:00',
        label: '补读文档',
        task_key: 'get_md:file_id=327',
      },
      {
        seq: 2,
        layer: 'kb' as const,
        node_id: 'get_md_worker',
        phase: 'start' as const,
        attempt: 1,
        ts: '2026-07-03T00:00:01+08:00',
        label: '补读文档',
        task_key: 'get_md:file_id=418',
      },
    ]
    const { nodes } = buildDisplayTopology(events, 'kb_full')
    const placements = computeKbFullPlacements(nodes)
    const worker327 = nodes.find((node) => node.taskKey === 'get_md:file_id=327')
    const worker418 = nodes.find((node) => node.taskKey === 'get_md:file_id=418')
    expect(worker327).toBeTruthy()
    expect(worker418).toBeTruthy()
    expect(placements.get(worker327!.id)!.left).toBe(placements.get(worker418!.id)!.left)
    expect(placements.get(worker327!.id)!.top).toBeLessThan(placements.get(worker418!.id)!.top)
    expect(placements.get(worker327!.id)!.top).toBeGreaterThan(280 + FLOW_NODE_HEIGHT)
  })

  it('keeps wiki on the main row after assess and away from worker lane', () => {
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
    const assess = placements.get(nodes.find((n) => n.templateId === 'assess')!.id)!
    const wiki = placements.get(nodes.find((n) => n.templateId === 'wiki_expand')!.id)!
    const worker = placements.get(nodes.find((n) => n.templateId === 'get_md_worker')!.id)!

    expect(wiki.top).toBe(assess.top)
    expect(wiki.left).toBeGreaterThan(assess.left)
    expect(worker.top).toBeGreaterThan(assess.top + FLOW_NODE_HEIGHT)
  })
})
