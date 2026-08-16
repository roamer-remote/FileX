import type { TooltipComponentOption } from "echarts"

type TooltipChrome = Pick<
  TooltipComponentOption,
  "backgroundColor" | "borderColor" | "borderWidth" | "textStyle" | "extraCssText"
>

function readTooltipCssVars() {
  const cs = getComputedStyle(document.documentElement)
  const pick = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback
  return {
    bg: pick("--tooltip-bg", "#e8f4fc"),
    bgTop: pick("--tooltip-bg-top", "#f4f9fd"),
    text: pick("--tooltip-text", "#1d1d1f"),
    border: pick("--tooltip-border", "rgba(0, 113, 227, 0.22)"),
    highlight: pick("--tooltip-highlight", "inset 0 1px 0 rgba(255, 255, 255, 0.92)"),
    shadow: pick(
      "--tooltip-shadow",
      "0 1px 2px rgba(0, 113, 227, 0.1), 0 6px 16px rgba(44, 44, 46, 0.1), 0 14px 36px -8px rgba(44, 44, 46, 0.16)",
    ),
  }
}

/** 图表 Tooltip 与全局 Ant Tooltip 共用 3D 浮层样式（淡蓝/深灰底、渐变、阴影） */
export function echartsTooltipChrome(_isDark: boolean): TooltipChrome {
  const t = readTooltipCssVars()
  return {
    backgroundColor: t.bg,
    borderColor: t.border,
    borderWidth: 1,
    textStyle: {
      color: t.text,
      fontSize: 12,
      lineHeight: 18,
    },
    extraCssText: [
      `background: linear-gradient(180deg, ${t.bgTop} 0%, ${t.bg} 100%) !important`,
      `border: 1px solid ${t.border} !important`,
      `border-radius: 4px !important`,
      `box-shadow: ${t.highlight}, ${t.shadow} !important`,
      "padding: 6px 10px !important",
    ].join("; "),
  }
}
