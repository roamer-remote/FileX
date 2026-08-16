import { describe, expect, it } from 'vitest'
import {
  defaultPipelineStages,
  parsePipelineJson,
  serializePipelineFromTable,
  type PipelineRouteRow,
} from './kbIngestionPipeline'

describe('kbIngestionPipeline', () => {
  it('returns empty routes for blank input', () => {
    const parsed = parsePipelineJson('')
    expect(parsed.routes).toEqual([])
    expect(parsed.stages).toEqual(defaultPipelineStages())
  })

  it('round-trips mime_prefix and ext routes', () => {
    const routes: PipelineRouteRow[] = [
      {
        key: 'r-0',
        matchKind: 'mime_prefix',
        mimePrefix: 'application/pdf',
        extensions: '',
        extractProvider: 'mineru',
      },
      {
        key: 'r-1',
        matchKind: 'ext',
        mimePrefix: '',
        extensions: '.docx, pptx',
        extractProvider: 'markitdown',
      },
    ]
    const stages = { entity_extract: true, wiki_lint_on_index: false }
    const json = serializePipelineFromTable(routes, stages)
    const parsed = parsePipelineJson(json)
    expect(parsed.routes).toHaveLength(2)
    expect(parsed.routes[0]).toMatchObject({
      matchKind: 'mime_prefix',
      mimePrefix: 'application/pdf',
      extractProvider: 'mineru',
    })
    expect(parsed.routes[1]).toMatchObject({
      matchKind: 'ext',
      extensions: '.docx, .pptx',
      extractProvider: 'markitdown',
    })
    expect(parsed.stages.entity_extract).toBe(true)
  })

  it('rejects invalid pipeline version', () => {
    expect(() => parsePipelineJson('{"version":2,"routes":[]}')).toThrow(/version/)
  })

  it('serializes an entity extraction toggle even when no route is configured', () => {
    const json = serializePipelineFromTable([], {
      entity_extract: true,
      wiki_lint_on_index: false,
    })

    expect(JSON.parse(json)).toMatchObject({
      version: 1,
      routes: [],
      stages: { entity_extract: true, wiki_lint_on_index: false },
    })
  })
})
