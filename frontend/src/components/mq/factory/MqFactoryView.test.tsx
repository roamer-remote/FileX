/**
 * @vitest-environment jsdom
 */

import { act } from 'react-dom/test-utils'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MqQueueStatus } from '@/api/admin'
import type { MqUserActiveTask } from '@/api/mq'
import MqFactoryView from './MqFactoryView'

vi.mock('@/hooks/useMqFactoryQueuedJobs', () => ({
  useMqFactoryQueuedJobs: () => ({}),
}))

function t(key: string, opts?: Record<string, unknown>) {
  const labels: Record<string, string> = {
    'admin.mq.groupExtract': '笔记生成',
    'admin.mq.groupIndex': '建立检索',
    'admin.mq.groupPost': '后处理',
    'admin.mq.factoryWorkshopSuffix': '车间',
    'admin.mq.factoryHealthIdle': '空闲',
    'admin.mq.factoryHealthRunning': '运行中',
    'admin.mq.factoryHealthBacklog': '积压',
    'admin.mq.factoryHealthAttention': '需关注',
    'admin.mq.backlogTotal': '未完成',
    'admin.mq.backlogQueued': '排队',
    'admin.mq.backlogRunning': '处理中',
    'admin.mq.factoryZoneQueue': '主队列',
    'admin.mq.factoryZoneProcess': '加工台',
    'admin.mq.factoryZoneRetry': '返工线',
    'admin.mq.factoryZoneDlq': '回收站',
    'admin.mq.factoryRobotStatus': '机器人状态',
    'admin.mq.factoryExpand': '展开特写',
    'admin.mq.factoryQueuePreviewTitle': '排队中',
    'admin.mq.factoryQueueItemWaiting': '等待',
    'admin.mq.factoryViewAllQueued': `查看全部 ${opts?.count ?? 0} 个`,
    'admin.mq.factoryResourceTitle': '系统负载',
    'admin.mq.factoryResourceRunning': '运行中',
    'admin.mq.factoryResourceCpu': 'CPU',
    'admin.mq.factoryResourceGpu': 'GPU',
    'admin.mq.factoryResourceVram': '显存',
    'admin.mq.factoryResourceProcessing': '当前处理',
    'admin.mq.factoryResourceCpuOnly': '仅 CPU',
    'admin.mq.factoryResourceCapabilityHigh': '高显存',
    'admin.mq.factoryResourceCapabilityMedium': '中显存',
    'admin.mq.factoryResourceCapabilityLow': '低显存',
    'admin.mq.factoryResourceCapabilityCpuOnly': '仅 CPU',
    'admin.mq.factoryResourceReasonNoCuda': 'CUDA 不可用',
    'admin.mq.factoryResourceReasonProbeFailed': 'CUDA 探针失败',
    'admin.mq.factoryResourceReasonInsufficientMemory': 'GPU 显存低于 8 GiB',
  }
  return labels[key] ?? key
}

function q(label: string, overrides: Partial<MqQueueStatus> = {}): MqQueueStatus {
  return {
    name: `queue.${label}`,
    label,
    online: true,
    message_count: 0,
    consumer_count: 1,
    consumer_busy: false,
    jobs_pending: 0,
    backlog_total: 0,
    ...overrides,
  }
}

const allQueues = [
  q('extract_main', { consumer_busy: true, backlog_total: 1 }),
  q('extract_retry'),
  q('extract_dlq'),
  q('index_main'),
  q('index_retry'),
  q('index_dlq'),
  q('post_main'),
  q('post_retry'),
  q('post_dlq'),
]

const activeTasks: MqUserActiveTask[] = [
  {
    kind: 'kb_extract',
    file_id: 1,
    filename: 'contract.pdf',
    model: 'MinerU',
  },
]

async function renderFactory(systemResources: {
  cpu_percent: number | null
  gpu: {
    available: boolean
    capability?: 'high' | 'medium' | 'low' | 'cpu_only'
    reason_code?: string | null
    name?: string
    util_percent?: number | null
    memory_used_mb?: number | null
    memory_total_mb?: number | null
  }
}) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root: Root = createRoot(container)
  await act(async () => {
    root.render(
      <MqFactoryView
        sortedQueues={allQueues}
        activeTasks={activeTasks}
        queuedPreviewsOverride={{}}
        mode="user"
        showSidecarStations={false}
        systemResources={systemResources}
        t={t}
        onViewMessages={() => undefined}
      />,
    )
  })
  return { root, container }
}

describe('MqFactoryView system resources', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows CPU, GPU, and VRAM in the running workshop only', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        gpu_usable: true,
        capability: 'high',
        name: 'NVIDIA RTX 4090',
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    expect(document.body.textContent).toContain('系统负载')
    expect(document.body.textContent).toContain('高显存')
    expect(document.body.textContent).toContain('CPU')
    expect(document.body.textContent).toContain('72%')
    expect(document.body.textContent).toContain('GPU')
    expect(document.body.textContent).toContain('86%')
    expect(document.body.textContent).toContain('NVIDIA')
    expect(document.body.textContent).toContain('18.4 / 24.0GB')
    expect(document.body.textContent).toContain('当前处理')
    expect(document.body.textContent).toContain('笔记生成 · MinerU')
    expect(document.body.querySelectorAll('.mq-figma-resource-panel')).toHaveLength(1)
  })

  it('renders the system resource panel at the enlarged readable size', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        gpu_usable: true,
        capability: 'high',
        name: 'NVIDIA RTX 4090',
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    const resourcePanel = document.body.querySelector('.mq-figma-resource-panel')
    const panel = resourcePanel?.parentNode as Element | null
    expect(panel).not.toBeNull()
    expect({
      x: panel?.getAttribute('x'),
      y: panel?.getAttribute('y'),
      width: panel?.getAttribute('width'),
      height: panel?.getAttribute('height'),
    }).toEqual({ x: '30', y: '352', width: '390', height: '196' })
  })

  it('hides GPU and VRAM rows when no NVIDIA GPU is available', async () => {
    await renderFactory({
      cpu_percent: 38,
      gpu: { available: false },
    })

    expect(document.body.textContent).toContain('系统负载')
    expect(document.body.textContent).toContain('38%')
    expect(document.body.textContent).toContain('当前处理')
    expect(document.body.textContent).toContain('笔记生成 · MinerU')
    expect(document.body.textContent).not.toContain('GPU')
    const resourceLabels = Array.from(document.body.querySelectorAll('.mq-figma-resource-row__label')).map((node) => node.textContent)
    expect(resourceLabels).not.toContain('GPU')
    expect(resourceLabels).not.toContain('显存')
  })

  it('shows physical GPU and VRAM rows even when scheduler reports CPU-only', async () => {
    await renderFactory({
      cpu_percent: 38,
      gpu: {
        available: true,
        gpu_usable: false,
        capability: 'cpu_only',
        reason_code: 'cpu_only_insufficient_memory',
        name: 'NVIDIA GTX 1080',
        util_percent: 42,
        memory_used_mb: 2048,
        memory_total_mb: 8192,
      },
    })

    expect(document.body.querySelector('.mq-figma-resource-panel__status')).toBeNull()
    expect(document.body.textContent).not.toContain('仅 CPU')
    const resourceLabels = Array.from(document.body.querySelectorAll('.mq-figma-resource-row__label')).map((node) => node.textContent)
    expect(resourceLabels).toContain('GPU')
    expect(resourceLabels).toContain('显存')
    expect(document.body.textContent).toContain('42%')
    expect(document.body.textContent).toContain('NVIDIA')
  })

  it('keeps the illustrated workshop interaction overlays when rendered over a bitmap', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    expect(document.body.querySelector('.mq-figma-row__background')).not.toBeNull()
    expect(document.body.querySelector('.mq-figma-bitmap-flow--running')).not.toBeNull()
    expect(document.body.querySelectorAll('.mq-figma-hit').length).toBeGreaterThanOrEqual(4)
  })

  it('uses one configured illustrated bitmap background per main pipeline', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    const backgrounds = Array.from(document.body.querySelectorAll('.mq-figma-row__background'))
      .map((node) => node.getAttribute('href') ?? node.getAttribute('xlink:href'))

    expect(backgrounds).toEqual([
      '/assets/mq-factory/illustrated/workshop-extract.png',
      '/assets/mq-factory/illustrated/workshop-index.png',
      '/assets/mq-factory/illustrated/workshop-post.png',
    ])
  })

  it('renders dynamic values directly on the cleaned bitmap without cover rectangles', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    expect(document.body.querySelector('.mq-figma-bitmap-cover')).toBeNull()
    expect(document.body.querySelector('.mq-figma-bitmap-counter rect')).toBeNull()
  })

  it('does not render parcel graphics over the illustrated bitmap conveyor', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    expect(document.body.querySelector('.mq-figma-bitmap-package')).toBeNull()
  })

  it('centers the health text within the bitmap status slot', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    const healthSlot = document.body.querySelector('.mq-figma-bitmap-hud__health-slot')
    const healthText = healthSlot?.querySelector('.mq-figma-bitmap-hud__health')

    expect(healthSlot?.tagName.toLowerCase()).toBe('foreignobject')
    expect(healthSlot?.getAttribute('x')).toBe('342')
    expect(healthSlot?.getAttribute('y')).toBe('25')
    expect(healthSlot?.getAttribute('width')).toBe('102')
    expect(healthSlot?.getAttribute('height')).toBe('44')
    expect(healthText).not.toBeNull()
  })

  it('centers every station counter inside its bitmap counter slot', async () => {
    await renderFactory({
      cpu_percent: 72,
      gpu: {
        available: true,
        util_percent: 86,
        memory_used_mb: 18841,
        memory_total_mb: 24564,
      },
    })

    const counters = Array.from(document.body.querySelectorAll('.mq-figma-bitmap-counter-slot'))

    expect(counters).toHaveLength(12)
    expect(
      counters.slice(0, 4).map((counter) => ({
        x: counter.getAttribute('x'),
        y: counter.getAttribute('y'),
        width: counter.getAttribute('width'),
        height: counter.getAttribute('height'),
      })),
    ).toEqual([
      { x: '482', y: '388', width: '152', height: '68' },
      { x: '919', y: '388', width: '154', height: '68' },
      { x: '1338', y: '388', width: '154', height: '68' },
      { x: '1648', y: '388', width: '154', height: '68' },
    ])
    for (const counter of counters) {
      expect(counter.tagName.toLowerCase()).toBe('foreignobject')
      expect(counter.querySelector('.mq-figma-bitmap-counter__value')).not.toBeNull()
    }
  })
})
