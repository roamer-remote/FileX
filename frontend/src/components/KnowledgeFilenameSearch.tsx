import { useCallback, useEffect, useRef, useState } from 'react'
import { Input } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'
import { useFilesStore } from '@/stores/filesStore'
import './KnowledgeFilenameSearch.css'

type BaseProps = {
  /** Enter 或点击搜索图标时触发（如打开资料页 Drawer） */
  onSubmit?: () => void
  className?: string
  placeholderKey?: string
  submitAriaLabelKey?: string
  size?: 'small' | 'middle' | 'large'
  variant?: 'outlined' | 'borderless' | 'filled' | 'underlined'
}

type StoreProps = BaseProps & {
  value?: undefined
  onChange?: undefined
  onClear?: undefined
}

type ControlledProps = BaseProps & {
  value: string
  onChange: (value: string) => void
  onClear?: () => void
}

type Props = StoreProps | ControlledProps

const DEBOUNCE_MS = 300

function FilenameSearchInput({
  value,
  onChange,
  onClear,
  onSubmit,
  className,
  placeholderKey,
  submitAriaLabelKey,
  size = 'small',
  variant = 'outlined',
}: BaseProps & {
  value: string
  onChange: (value: string) => void
  onClear?: () => void
}) {
  const { t } = useTranslation()

  const handleSubmit = useCallback(() => {
    onSubmit?.()
  }, [onSubmit])

  return (
    <Input
      allowClear
      size={size}
      variant={variant}
      className={['knowledge-filename-search', className].filter(Boolean).join(' ')}
      prefix={
        <button
          type="button"
          className="knowledge-filename-search__prefix-btn"
          onClick={handleSubmit}
          aria-label={t(submitAriaLabelKey ?? 'knowledge.searchOpenFilesHint')}
        >
          <SearchOutlined aria-hidden />
        </button>
      }
      placeholder={t(placeholderKey ?? 'fileList.searchPlaceholder')}
      aria-label={t(placeholderKey ?? 'fileList.searchPlaceholder')}
      title={t('fileList.searchTitle')}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onClear={() => {
        onChange('')
        onClear?.()
      }}
      onPressEnter={handleSubmit}
    />
  )
}

function KnowledgeFilenameSearchStore(props: StoreProps) {
  const { onSubmit, ...rest } = props
  const searchKeyword = useFilesStore((s) => s.searchKeyword)
  const searchFiles = useFilesStore((s) => s.search)
  const [draft, setDraft] = useState(searchKeyword)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setDraft(searchKeyword)
  }, [searchKeyword])

  const flushSearch = useCallback(
    (value: string) => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current)
        debounceRef.current = null
      }
      if (value !== searchKeyword) {
        searchFiles(value)
      }
    },
    [searchFiles, searchKeyword],
  )

  useEffect(() => {
    if (draft === searchKeyword) return
    debounceRef.current = setTimeout(() => flushSearch(draft), DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [draft, searchKeyword, flushSearch])

  const handleSubmit = useCallback(() => {
    flushSearch(draft)
    onSubmit?.()
  }, [draft, flushSearch, onSubmit])

  return (
    <FilenameSearchInput
      {...rest}
      value={draft}
      onChange={setDraft}
      onSubmit={handleSubmit}
    />
  )
}

export default function KnowledgeFilenameSearch(props: Props) {
  if (props.value !== undefined && props.onChange !== undefined) {
    const { value, onChange, onClear, ...rest } = props
    return (
      <FilenameSearchInput
        {...rest}
        value={value}
        onChange={onChange}
        onClear={onClear}
      />
    )
  }
  return <KnowledgeFilenameSearchStore {...props} />
}
