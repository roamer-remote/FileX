import { QuestionCircleOutlined } from '@ant-design/icons'
import { Tooltip } from 'antd'

type StatLabelWithHelpProps = {
  label: string
  help: string
  tooltipClassName?: string
}

/** 指标卡标题 + 悬停说明（class：stat-label-with-help，见 cyber.css） */
export default function StatLabelWithHelp({ label, help, tooltipClassName }: StatLabelWithHelpProps) {
  return (
    <span className="stat-label-with-help">
      <span className="stat-label-with-help__text">{label}</span>
      <Tooltip title={help} overlayClassName={tooltipClassName} styles={{ root: { maxWidth: 480 } }}>
        <button type="button" className="stat-label-with-help__btn" aria-label={help}>
          <QuestionCircleOutlined aria-hidden />
        </button>
      </Tooltip>
    </span>
  )
}
