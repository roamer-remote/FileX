import { useCallback, useRef, useState } from 'react'
import { Input } from 'antd'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import './KnowledgeLobbyToolbar.css'

type Props = {
  /** Enter / 搜索图标：打开智能检索 Drawer，并带入当前输入 */
  onOpenEval?: (query: string) => void
}

export default function KnowledgeLobbyToolbar({ onOpenEval }: Props) {
  const { t } = useTranslation()
  const [evalDraft, setEvalDraft] = useState('')
  const composingRef = useRef(false)

  const handleEvalSubmit = useCallback(() => {
    if (composingRef.current) return
    onOpenEval?.(evalDraft.trim())
  }, [evalDraft, onOpenEval])

  return (
    <header className="knowledge-lobby-toolbar" aria-label={t('knowledge.lobbyToolbarAria')}>
      <div className="knowledge-lobby-toolbar__eval-wrap">
        <div className="knowledge-lobby-google-bar knowledge-lobby-eval-search">
          <span className="knowledge-lobby-google-bar__lead" aria-hidden>
            <PlusOutlined />
          </span>
          <Input
            allowClear
            variant="borderless"
            className="knowledge-lobby-google-bar__input"
            placeholder={t('knowledge.lobbyEvalSearchPlaceholder')}
            aria-label={t('knowledge.lobbyToolbarSearchOpenEval')}
            value={evalDraft}
            onChange={(e) => setEvalDraft(e.target.value)}
            onCompositionStart={() => {
              composingRef.current = true
            }}
            onCompositionEnd={(e) => {
              composingRef.current = false
              setEvalDraft(e.currentTarget.value)
            }}
            onPressEnter={handleEvalSubmit}
          />
          <button
            type="button"
            className="knowledge-lobby-google-bar__ai-chip"
            onClick={handleEvalSubmit}
            aria-label={t('knowledge.lobbyToolbarSearchOpenEval')}
          >
            <SearchOutlined className="knowledge-lobby-google-bar__ai-chip-icon" aria-hidden />
            <span>{t('knowledge.lobbyEvalAiMode')}</span>
          </button>
        </div>
      </div>
    </header>
  )
}
