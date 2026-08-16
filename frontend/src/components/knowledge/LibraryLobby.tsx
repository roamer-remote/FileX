import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { useTranslation } from 'react-i18next'
import {
  LOBBY_BG_DESKTOP,
  LOBBY_BG_DESKTOP_DARK,
  LOBBY_BG_DESKTOP_FALLBACK,
  LOBBY_BG_MOBILE,
  LOBBY_BG_MOBILE_DARK,
  LOBBY_BG_MOBILE_FALLBACK,
} from '@/lib/knowledgePanelConfig'
import './LibraryLobby.css'

type Props = {
  showEmptyGuide: boolean
  zeroAclEmpty?: boolean
}

const FILEX_ATOM_ANCHOR = {
  light: { x: 950 / 1920, y: 952 / 1279 },
  dark: { x: 761 / 1536, y: 763 / 1024 },
} as const

const LOBBY_DESKTOP_IMAGE = {
  light: { width: 1920, height: 1279 },
  dark: { width: 1536, height: 1024 },
} as const

function getActiveLobbyTheme() {
  const theme = document.documentElement.getAttribute('data-theme')
  return theme === 'dark' ? 'dark' : 'light'
}

function calculateCoverAnchor(stage: HTMLElement): { x: number; y: number } {
  const { width, height } = stage.getBoundingClientRect()
  const theme = getActiveLobbyTheme()
  const image = LOBBY_DESKTOP_IMAGE[theme]
  const anchor = FILEX_ATOM_ANCHOR[theme]
  const scale = Math.max(width / image.width, height / image.height)
  const renderedWidth = image.width * scale
  const renderedHeight = image.height * scale
  const offsetX = (width - renderedWidth) * 0.5
  const offsetY = (height - renderedHeight) * 0.42

  return {
    x: offsetX + image.width * anchor.x * scale,
    y: offsetY + image.height * anchor.y * scale,
  }
}

function LobbyBackgroundPicture({
  className,
  desktopWebp,
  desktopFallback,
  mobileWebp,
  mobileFallback,
}: {
  className: string
  desktopWebp: string
  desktopFallback: string
  mobileWebp: string
  mobileFallback: string
}) {
  return (
    <picture className={className} aria-hidden>
      <source media="(max-width: 768px)" srcSet={mobileWebp} type="image/webp" />
      <source media="(max-width: 768px)" srcSet={mobileFallback} />
      <source srcSet={desktopWebp} type="image/webp" />
      <img className="library-lobby__bg-img" src={desktopFallback} alt="" decoding="async" />
    </picture>
  )
}

export default function LibraryLobby({ showEmptyGuide, zeroAclEmpty = false }: Props) {
  const { t } = useTranslation()
  const stageRef = useRef<HTMLDivElement | null>(null)
  const [atomPosition, setAtomPosition] = useState<{ x: number; y: number } | null>(null)

  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return undefined

    const updateAtomPosition = () => {
      const next = calculateCoverAnchor(stage)
      setAtomPosition((prev) => {
        if (prev && Math.abs(prev.x - next.x) < 0.5 && Math.abs(prev.y - next.y) < 0.5) {
          return prev
        }
        return next
      })
    }

    updateAtomPosition()
    const resizeObserver = new ResizeObserver(updateAtomPosition)
    resizeObserver.observe(stage)
    const themeObserver = new MutationObserver(updateAtomPosition)
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    })

    return () => {
      resizeObserver.disconnect()
      themeObserver.disconnect()
    }
  }, [])

  const atomStyle = atomPosition
    ? ({
        '--filex-atom-x': `${atomPosition.x}px`,
        '--filex-atom-y': `${atomPosition.y}px`,
      } as CSSProperties)
    : undefined

  return (
    <section
      className={'library-lobby library-lobby--light3d' + (showEmptyGuide ? ' library-lobby--empty' : '')}
      aria-label={t('knowledge.lobbyAria')}
    >
      <div ref={stageRef} className="library-lobby__stage">
        <LobbyBackgroundPicture
          className="library-lobby__bg library-lobby__bg--light"
          desktopWebp={LOBBY_BG_DESKTOP}
          desktopFallback={LOBBY_BG_DESKTOP_FALLBACK}
          mobileWebp={LOBBY_BG_MOBILE}
          mobileFallback={LOBBY_BG_MOBILE_FALLBACK}
        />
        <LobbyBackgroundPicture
          className="library-lobby__bg library-lobby__bg--dark"
          desktopWebp={LOBBY_BG_DESKTOP_DARK}
          desktopFallback={LOBBY_BG_DESKTOP_DARK}
          mobileWebp={LOBBY_BG_MOBILE_DARK}
          mobileFallback={LOBBY_BG_MOBILE_DARK}
        />
        <div className="library-lobby__filex-atom" style={atomStyle} aria-hidden="true">
          <span className="library-lobby__filex-atom-core" />
          <span className="library-lobby__filex-orbit-shell">
            <span className="library-lobby__filex-orbit library-lobby__filex-orbit--a">
              <span className="library-lobby__filex-electron" />
            </span>
            <span className="library-lobby__filex-orbit library-lobby__filex-orbit--b">
              <span className="library-lobby__filex-electron" />
            </span>
            <span className="library-lobby__filex-orbit library-lobby__filex-orbit--c">
              <span className="library-lobby__filex-electron" />
            </span>
            <span className="library-lobby__filex-orbit library-lobby__filex-orbit--d">
              <span className="library-lobby__filex-electron" />
            </span>
          </span>
        </div>
      </div>

      {zeroAclEmpty ? (
        <div className="library-lobby__empty">
          <p className="library-lobby__empty-title">{t('knowledge.zeroAclEmpty.title')}</p>
          <p className="library-lobby__empty-hint">{t('knowledge.zeroAclEmpty.hint')}</p>
        </div>
      ) : showEmptyGuide ? (
        <div className="library-lobby__empty">
          <p className="library-lobby__empty-title">{t('knowledge.lobbyEmpty.title')}</p>
          <p className="library-lobby__empty-hint">{t('knowledge.lobbyEmpty.hint')}</p>
        </div>
      ) : null}
    </section>
  )
}
