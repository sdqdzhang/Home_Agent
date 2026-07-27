/**
 * @typedef {Object} Agent
 * @property {string} id
 * @property {string} label
 * @property {string[]} names
 * @property {string} defaultMood
 * @property {string} icon
 * @property {string} description
 * @property {string[]} defaultMsgTypes
 */

/** @type {Agent[]} */
export const AGENTS = [
  {
    id: 'jarvis',
    label: '主对话',
    names: ['jarvis', 'Jarvis', '主对话'],
    defaultMood: '平静',
    icon: '◉',
    description: '日常聊天',
    defaultMsgTypes: ['text'],
  },
  {
    id: 'planning',
    label: '规划',
    names: ['规划模块', 'planning', 'planner'],
    defaultMood: '构思中',
    icon: '◎',
    description: '目标→质询/环境探测→TaskGraph→拓扑执行',
    defaultMsgTypes: ['plan_result', 'clarify_result', 'env_probe_result', 'plan_progress', 'graph_run_result', 'text'],
  },
  {
    id: 'emotion',
    label: '情感与状态',
    names: ['情感与性格状态模块', 'emotion', 'persona'],
    defaultMood: '平静',
    icon: '◌',
    description: '情感、性格与情绪状态的感知与表达',
    defaultMsgTypes: ['persona_state', 'text'],
  },
  {
    id: 'security',
    label: '安全检查',
    names: ['安全检查模块', 'security'],
    defaultMood: '警惕',
    icon: '⛨',
    description: '危险操作审批与安全策略校验',
    defaultMsgTypes: ['approval_request', 'security_yellow_log', 'security_lists_result', 'text'],
  },
  {
    id: 'env',
    label: '环境感知',
    names: ['环境感知模块', 'env_sense', 'env'],
    defaultMood: '观察中',
    icon: '◈',
    description: '系统与环境状态静默上报',
    defaultMsgTypes: ['system_status', 'desktop_screenshot', 'camera_capture'],
  },
  {
    id: 'memory',
    label: '记忆',
    names: ['记忆模块', 'memory'],
    defaultMood: '回忆中',
    icon: '◫',
    description: '记忆的写入、检索、压缩与反思',
    defaultMsgTypes: ['memory_record', 'text'],
  },
  {
    id: 'crawler',
    label: '网页爬取',
    names: ['网页爬取模块', 'crawler'],
    defaultMood: '待命',
    icon: '◍',
    description: '网页抓取、过滤预览，并可将正文保存为文件',
    defaultMsgTypes: ['execution_log'],
  },
  {
    id: 'rag',
    label: 'RAG',
    names: ['RAG模块', 'RAG 模块', 'rag'],
    defaultMood: '检索中',
    icon: '◬',
    description: '检索增强生成：查询、召回与回答',
    defaultMsgTypes: ['rag_result', 'text'],
  },
  {
    id: 'executor',
    label: '执行',
    names: ['执行模块', 'executor', 'execution'],
    defaultMood: '执行中',
    icon: '▶',
    description: '自然语言自动路由：命令 / 文件操作',
    defaultMsgTypes: ['execution_log'],
  },
  {
    id: 'processor',
    label: '处理',
    names: ['处理', 'processor'],
    defaultMood: '处理中',
    icon: '▦',
    description: '要求 + DataBlock 上下文 → 产出一个 DataBlock',
    defaultMsgTypes: ['datablock', 'text'],
  },
  {
    id: 'llm',
    label: '模型配置',
    names: ['本地Agent', 'local_agent', 'llm'],
    defaultMood: '就绪',
    icon: '⎇',
    description: 'Local Agent LLM 端点与槽位绑定',
    defaultMsgTypes: ['llm_config_result'],
  },
  {
    id: 'terminal',
    label: '远程终端',
    names: ['远程终端', 'terminal'],
    defaultMood: '在线',
    icon: '▤',
    description: '网页 cmd，直连本机 Shell（不经安全检查）',
    defaultMsgTypes: [],
  },
]

export const USER_SENDER = 'user_ui'
export const WS_TARGET = 'user_ui'

/** @param {string} name */
export function findAgentByName(name) {
  return AGENTS.find((a) => a.names.includes(name) || a.id === name)
}

/** @param {import('../utils/messages.js').UiMessage} msg */
export function resolveAgentForMessage(msg) {
  const byName = findAgentByName(msg.name)
  if (byName) return byName
  if (msg.name === USER_SENDER) {
    return findAgentByName(msg.target) || AGENTS[0]
  }
  if (msg.channel) {
    return AGENTS.find((a) => a.id === msg.channel) || null
  }
  return null
}

/** @param {string} id */
export function findAgentById(id) {
  return AGENTS.find((a) => a.id === id)
}
