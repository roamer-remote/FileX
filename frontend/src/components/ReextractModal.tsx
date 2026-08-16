import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { Alert, Modal, Radio, Typography } from "antd"
import type { FileItem } from "@/api/files"
import { getSelectableExtractProviders, type ExtractProvider, parseExtractProvider } from "@/utils/extractProviders"
import { isMarkdownFile } from "./FileListComponents"

export type ReextractProvider = ExtractProvider
export type ReextractProviderChoice = "system_default" | ExtractProvider

type Props = {
  open: boolean
  file: FileItem | null
  /** 当前用户有效默认引擎（系统设置 + 个人偏好合并） */
  effectiveProvider: ReextractProvider
  insavloReady?: boolean
  confirming?: boolean
  onCancel: () => void
  onConfirm: (provider: ReextractProvider | null, force: boolean) => void | Promise<void>
}

const PROVIDER_I18N_KEY: Record<ExtractProvider, string> = {
  legacy: "Legacy",
  liteparse: "Liteparse",
  docling: "Docling",
  mineru: "Mineru",
  insavlo: "Insavlo",
}

export { parseExtractProvider as resolveReextractDefaultProvider }

export default function ReextractModal({
  open,
  file,
  effectiveProvider,
  insavloReady,
  confirming,
  onCancel,
  onConfirm,
}: Props) {
  const { t } = useTranslation()
  const [choice, setChoice] = useState<ReextractProviderChoice>("system_default")
  const systemDefaultRef = useRef<HTMLSpanElement | null>(null)
  const openedForFileIdRef = useRef<number | null>(null)
  const isMarkdown = file ? isMarkdownFile(file) : false
  const isPdf =
    Boolean(file) &&
    (file!.mime_type === "application/pdf" ||
      file!.filename.toLowerCase().endsWith(".pdf") ||
      file!.original_name?.toLowerCase().endsWith(".pdf"))
  const effectiveLabel = t(`fileList.reextractProvider${PROVIDER_I18N_KEY[effectiveProvider]}`)

  useEffect(() => {
    if (!open) {
      openedForFileIdRef.current = null
      return
    }
    if (!file || isMarkdown) return
    if (openedForFileIdRef.current === file.id) return
    openedForFileIdRef.current = file.id
    setChoice("system_default")
    requestAnimationFrame(() => {
      systemDefaultRef.current?.scrollIntoView({ block: "nearest" })
    })
  }, [open, file, isMarkdown])

  const needsForce = Boolean(file?.has_md)

  const resolveProvider = (): ReextractProvider | null => {
    if (isMarkdown) return null
    return choice === "system_default" ? null : choice
  }

  return (
    <Modal
      open={open}
      title={t("fileList.reextractModalTitle")}
      onOk={() => void onConfirm(resolveProvider(), needsForce)}
      onCancel={onCancel}
      okText={t("common.confirm")}
      cancelText={t("common.cancel")}
      confirmLoading={confirming}
      destroyOnClose
    >
      {needsForce ? (
        <Alert type="warning" showIcon message={t("fileList.reextractOverwriteConfirm")} className="fl-reextract-warn" />
      ) : null}
      {isMarkdown ? (
        <Alert type="info" showIcon message={t("fileList.reextractMarkdownHint")} />
      ) : (
        <>
          {isPdf ? (
            <Alert type="info" showIcon message={t("fileList.reextractScanPdfMineruHint")} className="fl-reextract-warn" />
          ) : null}
          <Typography.Text type="secondary" className="fl-reextract-label">
            {t("fileList.reextractProviderLabel")}
          </Typography.Text>
          <Radio.Group
            value={choice}
            onChange={(e) => setChoice(e.target.value as ReextractProviderChoice)}
            className="fl-reextract-radio"
          >
            <Radio value="system_default">
              <span ref={systemDefaultRef} className="fl-reextract-option-head">
                <span className="fl-reextract-option-title">
                  {t("fileList.reextractProviderSystemDefaultOption", { engine: effectiveLabel })}
                </span>
              </span>
              <Typography.Paragraph type="secondary" className="fl-reextract-option-desc">
                {t("fileList.reextractProviderSystemDefaultDesc")}
              </Typography.Paragraph>
            </Radio>
            {getSelectableExtractProviders(insavloReady).map((value) => {
              const key = PROVIDER_I18N_KEY[value]
              return (
                <Radio key={value} value={value}>
                  <span className="fl-reextract-option-head">
                    <span className="fl-reextract-option-title">
                      {t(`fileList.reextractProvider${key}`)}
                    </span>
                  </span>
                  <Typography.Paragraph type="secondary" className="fl-reextract-option-desc">
                    {t(`fileList.reextractProvider${key}Desc`)}
                  </Typography.Paragraph>
                </Radio>
              )
            })}
          </Radio.Group>
        </>
      )}
    </Modal>
  )
}
