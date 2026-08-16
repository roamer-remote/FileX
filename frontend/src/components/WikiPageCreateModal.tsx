import { useEffect, useMemo, useState } from "react"
import { App, Form, Input, Modal, Select } from "antd"
import { useTranslation } from "react-i18next"
import { createWikiPage } from "@/api/knowledgeBase"
import { normalizeWikiSlug } from "@/utils/wikiSlug"
import "./WikiPageCreateModal.css"

type Props = {
  open: boolean
  onClose: () => void
  onCreated?: () => void
}

export default function WikiPageCreateModal({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [form] = Form.useForm<{ title: string; wiki_slug: string; page_kind: string; markdown: string }>()
  const [saving, setSaving] = useState(false)
  const title = Form.useWatch("title", form)

  const slugPreview = useMemo(() => normalizeWikiSlug(title || ""), [title])

  useEffect(() => {
    if (!open) return
    form.setFieldsValue({ title: "", wiki_slug: "", page_kind: "concept", markdown: "" })
  }, [open, form])

  useEffect(() => {
    if (slugPreview) form.setFieldValue("wiki_slug", slugPreview)
  }, [slugPreview, form])

  const submit = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      await createWikiPage({
        title: values.title.trim(),
        wiki_slug: normalizeWikiSlug(values.wiki_slug || values.title),
        page_kind: values.page_kind as "entity" | "concept" | "synthesis",
        markdown: values.markdown || "",
      })
      message.success(t("wikiCompile.createSuccess"))
      onClose()
      onCreated?.()
    } catch {
      /* axios 拦截器已提示 */
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title={t("wikiCompile.createTitle")}
      okText={t("wikiCompile.createSubmit")}
      cancelText={t("common.cancel")}
      confirmLoading={saving}
      onCancel={onClose}
      onOk={() => void submit()}
      destroyOnClose
      width={640}
      className="wiki-page-create-modal"
    >
      <p className="wiki-page-create-hint">{t("wikiCompile.createHint")}</p>
      <Form form={form} layout="vertical" requiredMark="optional">
        <Form.Item name="title" label={t("wikiCompile.fieldTitle")} rules={[{ required: true, message: t("wikiCompile.titleRequired") }]}>
          <Input placeholder={t("wikiCompile.fieldTitlePlaceholder")} maxLength={500} />
        </Form.Item>
        <Form.Item name="wiki_slug" label={t("wikiCompile.fieldSlug")} extra={t("wikiCompile.fieldSlugHint")}>
          <Input readOnly className="wiki-page-slug-readonly" />
        </Form.Item>
        <Form.Item name="page_kind" label={t("wikiCompile.fieldKind")}>
          <Select
            options={[
              { value: "concept", label: t("wikiCompile.kindConcept") },
              { value: "entity", label: t("wikiCompile.kindEntity") },
              { value: "synthesis", label: t("wikiCompile.kindSynthesis") },
            ]}
          />
        </Form.Item>
        <Form.Item name="markdown" label={t("wikiCompile.fieldMarkdown")}>
          <Input.TextArea rows={8} placeholder={t("wikiCompile.fieldMarkdownPlaceholder")} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
