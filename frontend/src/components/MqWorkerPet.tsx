import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CloseOutlined } from '@ant-design/icons'
import { Tooltip } from 'antd'
import { useTranslation } from 'react-i18next'
import type { MqStatusPayload } from '@/api/admin'
import { mqActiveTaskUsername } from '@/api/mq'
import { useMqStatus } from '@/providers/MqStatusProvider'
import { patchMqPetUiState } from '@/lib/uiStateSync'
import { MarqueeTooltip } from '@/components/FileListComponents'
import { storageFilenameDisplayName } from '@/utils/storageFilename'
import MqRobotPetSprite from './MqRobotPetSprite'
import './MqWorkerPet.css'

const POS_STORAGE_KEY = 'filex_mq_pet_pos'
const PET_W = 148
const PET_H = 188
const EDGE = 12
const EXTRACT_TASK_KINDS = new Set(['kb_extract', 'kb_mineru', 'kb_docling'])
const EXTRACT_QUEUE_LABELS = new Set(['extract_main', 'mineru_main', 'docling_main'])

type Point = { x: number; y: number }

function loadStoredPos(): Point | null {
  try {
    const raw = localStorage.getItem(POS_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Point
    if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') return parsed
  } catch {
    /* ignore */
  }
  return null
}

function defaultPos(): Point {
  if (typeof window === 'undefined') return { x: 24, y: 24 }
  return {
    x: Math.max(EDGE, window.innerWidth - PET_W - 24),
    y: EDGE,
  }
}

function clampPos(pos: Point): Point {
  if (typeof window === 'undefined') return pos
  const maxX = Math.max(EDGE, window.innerWidth - PET_W - EDGE)
  const maxY = Math.max(EDGE, window.innerHeight - PET_H - EDGE)
  return {
    x: Math.min(Math.max(EDGE, pos.x), maxX),
    y: Math.min(Math.max(EDGE, pos.y), maxY),
  }
}

function mqConsumerBusy(data: MqStatusPayload | null) {
  return data?.queues.some((q) => q.consumer_busy) ?? false
}

/** 提取正文 / MinerU 解析时使用机器人 pet；仅索引等其他任务时保持 logo pet。 */
function shouldUseRobotPet(data: MqStatusPayload | null): boolean {
  const tasks = data?.active_tasks ?? []
  if (tasks.some((task) => EXTRACT_TASK_KINDS.has(task.kind))) return true
  if (tasks.length > 0) return false
  return (data?.queues ?? []).some(
    (q) => q.consumer_busy && EXTRACT_QUEUE_LABELS.has(q.label),
  )
}

function taskKindDescription(kind: string, t: (key: string) => string): string {
  if (kind === 'kb_extract') return t('mqPet.taskExtract')
  if (kind === 'kb_mineru') return t('mqPet.taskMineru')
  if (kind === 'kb_docling') return t('mqPet.taskDocling')
  if (kind === 'kb_post') return t('mqPet.taskPost')
  if (kind === 'kb_index') return t('mqPet.taskIndex')
  return t('mqPet.taskIndex')
}

type PetBubbleText =
  | { mode: 'working'; username: string; taskDesc: string; filename: string; filenameFull: string }
  | { mode: 'idle'; text: string }

function PetBubbleLine({ text, variant }: { text: string; variant?: 'user' | 'desc' }) {
  const className =
    'mq-worker-pet__bubble-line' +
    (variant === 'user' ? ' mq-worker-pet__bubble-line--user' : '') +
    (variant === 'desc' ? ' mq-worker-pet__bubble-line--desc' : '')
  return <div className={className}>{text}</div>
}

function PetBubbleMarqueeLine({ text }: { text: string }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const measureRef = useRef<HTMLSpanElement>(null)
  const [marquee, setMarquee] = useState(false)
  const [durationSec, setDurationSec] = useState(8)

  useEffect(() => {
    const viewport = viewportRef.current
    const measure = measureRef.current
    if (!viewport || !measure) return

    const overflow = measure.scrollWidth > viewport.clientWidth + 1
    setMarquee(overflow)
    if (overflow) {
      const distance = measure.scrollWidth - viewport.clientWidth
      setDurationSec(Math.max(6, distance / 22))
    }
  }, [text])

  return (
    <MarqueeTooltip active={marquee} title={text}>
      <div className="mq-worker-pet__marquee" ref={viewportRef}>
        <span ref={measureRef} className="mq-worker-pet__marquee-measure" aria-hidden>
          {text}
        </span>
        {marquee ? (
          <div
            className="mq-worker-pet__marquee-track"
            style={{ animationDuration: `${durationSec}s` }}
          >
            <span className="mq-worker-pet__marquee-text">{text}</span>
            <span className="mq-worker-pet__marquee-text" aria-hidden>
              {text}
            </span>
          </div>
        ) : (
          <span className="mq-worker-pet__marquee-text">{text}</span>
        )}
      </div>
    </MarqueeTooltip>
  )
}

function petWorkingBubble(
  data: MqStatusPayload | null,
  t: (key: string, opts?: Record<string, string>) => string,
): PetBubbleText {
  const tasks = data?.active_tasks ?? []
  if (!tasks.length) {
    return { mode: 'idle', text: t('mqPet.working') }
  }

  const users = [
    ...new Set(tasks.map((task) => mqActiveTaskUsername(task)).filter((name): name is string => Boolean(name))),
  ]
  const kinds = [...new Set(tasks.map((task) => task.kind))]
  const taskDesc = kinds.map((kind) => taskKindDescription(kind, t)).join('、')
  const filenamesFull = [
    ...new Set(
      tasks
        .map((task) => task.filename?.trim())
        .filter((name): name is string => Boolean(name)),
    ),
  ]
  const filenamesDisplay = filenamesFull.map(storageFilenameDisplayName)

  return {
    mode: 'working',
    username: users.join('、'),
    taskDesc,
    filename: filenamesDisplay.length ? filenamesDisplay.join('、') : t('mqPet.unknownFile'),
    filenameFull: filenamesFull.length ? filenamesFull.join('、') : t('mqPet.unknownFile'),
  }
}

export default function MqWorkerPet() {
  const { t } = useTranslation()
  const { data } = useMqStatus()
  const busy = mqConsumerBusy(data)
  const [dismissed, setDismissed] = useState(false)
  const [mounted, setMounted] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const [pos, setPos] = useState<Point>(() => clampPos(loadStoredPos() ?? defaultPos()))
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; origin: Point } | null>(null)
  const shouldShow = busy && !dismissed
  const robotPet = useMemo(() => shouldUseRobotPet(data), [data])
  const bubbleText = useMemo(() => petWorkingBubble(data, t), [data, t])
  const statusLabel =
    bubbleText.mode === 'working'
      ? `${t('mqPet.reportPrefix')}${bubbleText.username}\n${t('mqPet.taskPrefix')}${bubbleText.taskDesc}\n${t('mqPet.filenameLabel')}${bubbleText.filename}`
      : bubbleText.text

  useEffect(() => {
    if (!busy) setDismissed(false)
  }, [busy])

  useEffect(() => {
    if (shouldShow) {
      setMounted(true)
      setLeaving(false)
      return
    }
    if (!mounted) return
    setLeaving(true)
    const timer = window.setTimeout(() => {
      setMounted(false)
      setLeaving(false)
    }, 280)
    return () => window.clearTimeout(timer)
  }, [shouldShow, mounted])

  useEffect(() => {
    const onResize = () => setPos((prev) => clampPos(prev))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const persistPos = useCallback((next: Point) => {
    const clamped = clampPos(next)
    setPos(clamped)
    try {
      localStorage.setItem(POS_STORAGE_KEY, JSON.stringify(clamped))
      patchMqPetUiState()
    } catch {
      /* ignore */
    }
  }, [])

  const dismissPet = () => {
    setDismissed(true)
  }

  const onPointerDown = (ev: React.PointerEvent<HTMLDivElement>) => {
    if (ev.button !== 0) return
    if ((ev.target as HTMLElement).closest('.mq-worker-pet__close')) return
    dragRef.current = {
      pointerId: ev.pointerId,
      startX: ev.clientX,
      startY: ev.clientY,
      origin: pos,
    }
    ev.currentTarget.setPointerCapture(ev.pointerId)
  }

  const onPointerMove = (ev: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== ev.pointerId) return
    persistPos({
      x: drag.origin.x + (ev.clientX - drag.startX),
      y: drag.origin.y + (ev.clientY - drag.startY),
    })
  }

  const onPointerUp = (ev: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || drag.pointerId !== ev.pointerId) return
    dragRef.current = null
    if (ev.currentTarget.hasPointerCapture(ev.pointerId)) {
      ev.currentTarget.releasePointerCapture(ev.pointerId)
    }
  }

  if (!mounted) return null

  return (
    <div
      className={
        'mq-worker-pet' +
        (robotPet ? ' mq-worker-pet--robot' : '') +
        (leaving ? ' mq-worker-pet--leaving' : '')
      }
      style={{ left: pos.x, top: pos.y }}
      role="status"
      aria-live="polite"
      aria-label={statusLabel}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <button
        type="button"
        className="mq-worker-pet__close"
        aria-label={t('mqPet.closeAria')}
        title={t('mqPet.closeAria')}
        onClick={dismissPet}
        onPointerDown={(ev) => ev.stopPropagation()}
      >
        <CloseOutlined aria-hidden />
      </button>
      <div className="mq-worker-pet__bubble">
        {bubbleText.mode === 'working' ? (
          <>
            <PetBubbleLine text={`${t('mqPet.reportPrefix')}${bubbleText.username}`} variant="user" />
            <PetBubbleLine text={`${t('mqPet.taskPrefix')}${bubbleText.taskDesc}`} variant="desc" />
            <Tooltip title={bubbleText.filenameFull} placement="topLeft" mouseEnterDelay={0.35}>
              <div className="mq-worker-pet__filename-row">
                <span className="mq-worker-pet__filename-label">{t('mqPet.filenameLabel')}</span>
                <PetBubbleMarqueeLine text={bubbleText.filename} />
              </div>
            </Tooltip>
          </>
        ) : (
          <PetBubbleLine text={bubbleText.text} />
        )}
      </div>
      <div className="mq-worker-pet__sprite" aria-hidden>
        <div className="mq-worker-pet__sprite-inner">
          <div className="mq-worker-pet__logo-shell">
            <span className="mq-worker-pet__spark mq-worker-pet__spark--a" />
            <span className="mq-worker-pet__spark mq-worker-pet__spark--b" />
            {robotPet ? (
              <MqRobotPetSprite />
            ) : (
              <>
                <img
                  src="/filex-logo.png"
                  alt=""
                  className="mq-worker-pet__logo"
                  decoding="async"
                  draggable={false}
                />
                <div className="mq-worker-pet__filex-atom" aria-hidden="true">
                  <span className="mq-worker-pet__filex-atom-core" />
                  <span className="mq-worker-pet__filex-orbit mq-worker-pet__filex-orbit--a">
                    <span className="mq-worker-pet__filex-electron" />
                  </span>
                  <span className="mq-worker-pet__filex-orbit mq-worker-pet__filex-orbit--b">
                    <span className="mq-worker-pet__filex-electron" />
                  </span>
                  <span className="mq-worker-pet__filex-orbit mq-worker-pet__filex-orbit--c">
                    <span className="mq-worker-pet__filex-electron" />
                  </span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
