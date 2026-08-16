import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { App, Tooltip } from "antd"
import { buildDingSkillInstallPrompt, fetchAgentSkillInstallPrompt } from "@/lib/agentSkillInstall"
import { copyToClipboard } from "@/utils/copyToClipboard"
import "./AgentSkillInstallPrompt.css"

function AgentSkillDeployIcon() {
  return (
    <svg
      className="agent-skill-deploy-icon"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <g className="agent-skill-deploy-icon__body">
        <rect x="6" y="8" width="12" height="11" rx="2.5" stroke="currentColor" strokeWidth="1.4" />
        <circle cx="9.5" cy="12.5" r="1" fill="currentColor" />
        <circle cx="14.5" cy="12.5" r="1" fill="currentColor" />
        <path
          d="M10 15.5h4"
          stroke="currentColor"
          strokeWidth="1"
          strokeLinecap="round"
          opacity="0.45"
        />
        <path d="M12 8V6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        <circle cx="12" cy="5" r="1" fill="currentColor" opacity="0.6" />
      </g>
      <g className="agent-skill-deploy-icon__packet">
        <rect x="1" y="10" width="5" height="4" rx="0.8" stroke="currentColor" strokeWidth="1.1" />
        <path
          d="M2 11.5h3"
          stroke="currentColor"
          strokeWidth="0.8"
          strokeLinecap="round"
          opacity="0.6"
        />
      </g>
    </svg>
  )
}

type AgentSkillInstallPromptProps = {
  /** 顶栏工具簇：动画图标按钮 */
  variant?: "inline" | "nav"
}

export default function AgentSkillInstallPrompt({ variant = "inline" }: AgentSkillInstallPromptProps) {
  const { message: msg } = App.useApp()
  const { t } = useTranslation()

  const [installText, setInstallText] = useState('')

  useEffect(() => {
    let cancelled = false
    fetchAgentSkillInstallPrompt(window.location.origin)
      .then((text) => {
        if (!cancelled) setInstallText(text)
      })
      .catch(() => {
        if (!cancelled) {
          setInstallText(buildDingSkillInstallPrompt(window.location.origin))
        }
      })
    return () => { cancelled = true }
  }, [])

  const onCopy = useCallback(async () => {
    if (!installText) return
    try {
      await copyToClipboard(installText)
      msg.success(t("knowledge.agentSkillInstall.copySuccess"))
    } catch {
      msg.error(t("knowledge.agentSkillInstall.copyFailed"))
    }
  }, [installText, msg, t])

  const isNav = variant === "nav"

  const tooltip = (
    <div>
      <div>{t("knowledge.agentSkillInstall.tooltipLine1")}</div>
      <div>{t("knowledge.agentSkillInstall.tooltipLine2")}</div>
    </div>
  )

  return (
    <div className={"agent-skill-install" + (isNav ? " agent-skill-install--nav" : "")}>
      <Tooltip title={tooltip} placement={isNav ? "bottom" : "topLeft"}>
        <button
          type="button"
          className={isNav ? "agent-skill-install-nav-btn" : "agent-skill-install-hint"}
          onClick={() => void onCopy()}
          aria-label={t("knowledge.agentSkillInstall.title")}
        >
          {isNav ? <AgentSkillDeployIcon /> : t("knowledge.agentSkillInstall.hint")}
        </button>
      </Tooltip>
    </div>
  )
}
