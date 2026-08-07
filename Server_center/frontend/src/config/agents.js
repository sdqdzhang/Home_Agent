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
    id: 'main',
    label: '主对话',
    names: ['main', '主对话'],
    defaultMood: '平静',
    icon: '◉',
    description: '主对话：聊天 + Function Calling 编排（规划/执行/RAG/环境/扩展）',
    defaultMsgTypes: [
      'text',
      'tool_result',
      'planning_session',
      'clarify_request',
      'plan_result',
      'clarify_result',
      'plan_progress',
      'graph_run_result',
      'execution_log',
      'system_status',
      'desktop_screenshot',
      'camera_capture',
    ],
  },
  {
    id: 'conversation_manager',
    label: '会话管理',
    names: ['会话管理', 'conversation_manager', 'cm'],
    defaultMood: '观察中',
    icon: '☰',
    description: '会话生命周期：规则触发 Analyzer、Conversation State、记忆候选与指标',
    defaultMsgTypes: ['cm_snapshot', 'cm_event', 'text'],
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
    description: '心智与状态：人格即插即用、情绪连续性、Mind Context',
    defaultMsgTypes: ['mind_snapshot', 'persona_state', 'text'],
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
    description: '系统采集与摘要；主对话仅在主动工具调用时展示结果',
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
    description: '网页抓取（主对话扩展工具）；过滤预览，可将正文保存为文件',
    defaultMsgTypes: ['execution_log'],
    extension: true,
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
