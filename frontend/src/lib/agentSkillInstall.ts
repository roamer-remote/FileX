/** 安装指令中 API Key 占位符（无 key 时供旧入口使用） */
export const DING_SKILL_INSTALL_API_KEY_PLACEHOLDER = 'FILEX_API_KEY=fb_完整密钥'

export type DingSkillInstallOptions = {
  apiKey?: string
}

/** 客户端默认安装提示文本（兜底，实际以服务端系统参数为准）。与服务端 DEFAULTS 保持同步。 */
export const DEFAULT_AGENT_SKILL_INSTALL_PROMPT = `请为我安装「钉」智能体技能（FileX 资料库，斜杠 /ding），适用于 OpenClaw、Hermes、OpenHuman、WorkBuddy、Claude Code、Codex、Cursor 等智能体。

站点根 URL：{{ORIGIN}}

请按顺序执行：
1. 下载技能包（无需鉴权）：
   curl -fsSL "{{ORIGIN}}/filex-skill-update" -o /tmp/filex-skill.zip
2. 解压到本智能体的 skills 根目录，使得到：
   skills/ding/SKILL.md
   skills/ding/modules/
   skills/ding/references/filex-agent-api.md
   （覆盖旧文件；skills 目录以你当前运行环境为准，例如 Hermes ~/.hermes/skills、Cursor ~/.cursor/skills 或项目 .cursor/skills）
3. 若需「链接 URL 入库」，另下载参考实现（.py 模板）：
   curl -fsSL "{{ORIGIN}}/filex-skill-agent-update" -o /tmp/filex-skill-agent.zip
   unzip -o /tmp/filex-skill-agent.zip -d <skills根目录>
   得到 skills/ding/agent/filex_ingest_url.py 后执行：
   pip install -r skills/ding/agent/requirements.txt
   playwright install chromium
   （详见 skills/ding/modules/url-ingest.md）
4. 配置 FileX 鉴权（库内检索/入库必需；外网 research 可暂不配）：
   - 环境变量：FILEX_ORIGIN={{ORIGIN}}（无尾部斜杠）、FILEX_API_KEY={{API_KEY}}（FileX Web「API 密钥」创建并 reveal；勿用登录 JWT）
   - Hermes：编辑 ~/.hermes/.env 写入上述两行；改后重启 Gateway
   - 其它平台（Cursor/Codex/Claude Code/OpenClaw/WorkBuddy 等）：在智能体宿主进程可读的位置配置同名环境变量
   - 验证：curl -s -H "Authorization: Bearer $FILEX_API_KEY" "$FILEX_ORIGIN/api/external/api-key-status" 应返回 valid:true 与 username
   - 已安装 agent 会在每次调用钉入口前自动检查更新，仅当版本/SHA256 不一致时才下载并校验 zip；改 env 后无需重装 zip
5. 安装完成后创建「钉安装备忘」，以后新对话先读备忘，不重复安装：
   - 推荐位置：Hermes 写 ~/.hermes/skills/ding/INSTALLATION.md；Codex/Claude Code/Cursor 写项目 .agent/ding-installation.md；其它平台写入长期记忆/skills notes
   - 记录：FILEX_ORIGIN、skills/ding 路径、skill 版本、skill_zip_sha256、agent_version、agent_zip_sha256、调用方式、依赖状态、验证结果、环境变量配置位置
   - 安全：备忘不写完整 FILEX_API_KEY，只记录 fb_...末尾4位和配置位置
6. 升级后检查版本匹配：
   - 本地：LOCAL_SKILL_VERSION="$(tr -d '[:space:]' < <skills根目录>/ding/skill.version)"
   - 服务器：SERVER_SKILL_VERSION="$(curl -fsS -H "Authorization: Bearer $FILEX_API_KEY" "$FILEX_ORIGIN/api/filex-skill/manifest" | python3 -c 'import json,sys; print(json.load(sys.stdin)["skill_version"])')"
   - 必须满足 test "$LOCAL_SKILL_VERSION" = "$SERVER_SKILL_VERSION"；不一致时勿宣称安装/升级完成。`

/**
 * 从服务端获取智能体技能安装提示文本（系统参数配置）。
 * 服务端支持 Redis 缓存，优先返回缓存内容。
 */
export async function fetchAgentSkillInstallPrompt(
  origin: string,
  options?: DingSkillInstallOptions,
): Promise<string> {
  const apiKey = options?.apiKey?.trim() || ''
  const baseOrigin = origin.replace(/\/$/, '')

  try {
    const resp = await fetch(
      `${baseOrigin}/api/settings/agent-skill-install-prompt`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ origin: baseOrigin, api_key: apiKey }),
      },
    )
    if (resp.ok) {
      const data = await resp.json()
      if (data?.prompt) return data.prompt
    }
  } catch {
    // fall through to default
  }

  // Fallback: render default template locally
  return renderDefaultPrompt(origin, options)
}

function renderDefaultPrompt(origin: string, options?: DingSkillInstallOptions): string {
  const base = origin.replace(/\/$/, '')
  const apiKeyValue = options?.apiKey?.trim()
  const apiKeyLine = apiKeyValue
    ? `FILEX_API_KEY=${apiKeyValue}`
    : DING_SKILL_INSTALL_API_KEY_PLACEHOLDER

  return DEFAULT_AGENT_SKILL_INSTALL_PROMPT
    .replace(/\{\{ORIGIN\}\}/g, () => base)
    .replace(/\{\{API_KEY\}\}/g, () => apiKeyLine)
}

/** @deprecated 使用 fetchAgentSkillInstallPrompt */
export function buildDingSkillInstallPrompt(
  origin: string,
  options?: DingSkillInstallOptions,
): string {
  return renderDefaultPrompt(origin, options)
}

/** @deprecated 使用 buildDingSkillInstallPrompt */
export const buildFileXSkillInstallPrompt = buildDingSkillInstallPrompt

/** @deprecated 使用 buildDingSkillInstallPrompt */
export const buildPubmedSkillInstallPrompt = buildDingSkillInstallPrompt
