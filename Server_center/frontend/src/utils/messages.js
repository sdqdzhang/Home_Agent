import { USER_SENDER, findAgentByName } from '../config/agents.js'

/** @typedef {{ id: string, name: string, target: string, msg_type: string, message: any, timestamp: number, status?: string, response?: any, channel?: string }} UiMessage */

/** @param {UiMessage} msg @param {{ id: string, names: string[] }} agent */
export function belongsToAgent(msg, agent) {
  if (msg.channel === agent.id) return true
  if (agent.names.includes(msg.name) || msg.name === agent.id) return true
  if (msg.name === USER_SENDER && (msg.target === agent.id || agent.names.includes(msg.target))) {
    return true
  }
  return false
}

/** @param {UiMessage} msg */
export function isUserMessage(msg) {
  return msg.name === USER_SENDER || msg.message?.role === 'user'
}

/** @param {UiMessage} msg */
export function messageSummary(msg) {
  const text = msg.message?.text || msg.message?.summary || msg.message?.query || ''
  if (text) return text.length > 42 ? `${text.slice(0, 42)}…` : text
  if (msg.msg_type === 'approval_request') return '⚠ 待审批请求'
  if (msg.msg_type === 'security_yellow_log') return msg.message?.payload?.command || '黄色记录'
  if (msg.msg_type === 'execution_log') return msg.message?.summary || '执行日志'
  if (msg.msg_type === 'system_status') {
    if (msg.message?.alert) return `⚠ ${msg.message?.alert_reason || msg.message?.text || '系统告警'}`
    return msg.message?.text || '系统状态更新'
  }
  if (msg.msg_type === 'desktop_screenshot') return '远程桌面截图'
  if (msg.msg_type === 'camera_capture') return '摄像头拍照'
  if (msg.msg_type === 'persona_state') return msg.message?.mood || '状态更新'
  if (msg.msg_type === 'rag_result') return msg.message?.query || 'RAG 检索结果'
  if (msg.msg_type === 'llm_config_result') {
    return msg.message?.ok ? '模型配置已更新' : '模型配置失败'
  }
  if (msg.msg_type === 'plan_result') return msg.message?.goal || msg.message?.summary || '任务规划'
  if (msg.msg_type === 'reflection_note') return msg.message?.issue || '自省记录'
  if (msg.msg_type === 'memory_record') return msg.message?.key || '记忆写入'
  return `[${msg.msg_type}]`
}

/** @param {UiMessage} msg */
export function countsAsUnread(msg) {
  return msg.msg_type !== 'system_status' && msg.msg_type !== 'persona_state' && msg.msg_type !== 'llm_config_result'
}

/** @param {UiMessage[]} messages @param {{ id: string }} agent */
export function hasEnvAlert(messages, agent) {
  if (agent.id !== 'env') return false
  return extractEnvDashboard(messages, agent).alert
}

/** @param {UiMessage} msg @param {{ id: string }} agent */
export function isUrgentUnread(msg, agent) {
  return (
    agent.id === 'security' &&
    msg.msg_type === 'approval_request' &&
    msg.status === 'pending' &&
    belongsToAgent(msg, agent)
  )
}

/** @param {UiMessage[]} messages @param {{ id: string }} agent */
export function isAgentWorking(messages, agent) {
  const recent = messages
    .filter((m) => belongsToAgent(m, agent))
    .sort((a, b) => b.timestamp - a.timestamp)[0]
  if (!recent) return false
  const age = Date.now() / 1000 - recent.timestamp
  if (recent.msg_type === 'execution_log' && recent.message?.status === 'running') return true
  if (['execution_log', 'rag_result'].includes(recent.msg_type) && age < 30) return true
  if (recent.msg_type !== 'system_status' && recent.msg_type !== 'persona_state' && age < 12) {
    return true
  }
  return false
}

/** @param {UiMessage[]} messages @param {{ id: string, defaultMood?: string }} agent */
export function agentMood(messages, agent) {
  if (agent.id === 'emotion') {
    const latest = messages
      .filter((m) => belongsToAgent(m, agent) && (m.message?.mood || m.msg_type === 'persona_state'))
      .sort((a, b) => b.timestamp - a.timestamp)[0]
    return latest?.message?.mood || agent.defaultMood
  }
  const latest = messages
    .filter((m) => belongsToAgent(m, agent) && m.message?.mood)
    .sort((a, b) => b.timestamp - a.timestamp)[0]
  return latest?.message?.mood || agent.defaultMood
}

/** @param {UiMessage[]} messages */
export function globalEmotionMood(messages) {
  const emotion = messages
    .filter(
      (m) =>
        (m.msg_type === 'persona_state' || m.message?.mood) &&
        ['情感与性格状态模块', 'emotion', 'persona'].includes(m.name),
    )
    .sort((a, b) => b.timestamp - a.timestamp)[0]
  return emotion?.message?.mood || null
}

/** @param {UiMessage[]} list */
export function sortMessagesAsc(list) {
  return [...list].sort((a, b) => a.timestamp - b.timestamp)
}

/** 环境模块对话区：仅 text / desktop_screenshot，不含 system_status 流 */
/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function envChatMessages(messages, agent) {
  return messages.filter(
    (m) =>
      belongsToAgent(m, agent) &&
      (m.msg_type === 'text' || m.msg_type === 'desktop_screenshot' || m.msg_type === 'camera_capture'),
  )
}

/** RAG 对话区：用户提问 + rag_result 回答（不含入库 execution_log） */
/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function ragChatMessages(messages, agent) {
  return messages.filter(
    (m) =>
      belongsToAgent(m, agent) &&
      (m.msg_type === 'text' || m.msg_type === 'rag_result') &&
      !isRagIngestRequest(m),
  )
}

/** RAG 入库日志（execution_log，按时间倒序） */
/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent @param {number} limit */
export function ragIngestLogs(messages, agent, limit = 30) {
  return messages
    .filter((m) => belongsToAgent(m, agent) && m.msg_type === 'execution_log')
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, limit)
}

/** 是否为用户发起的 RAG 入库请求（用于从对话区隐藏） */
/** @param {UiMessage} msg */
export function isRagIngestRequest(msg) {
  const action = msg.message?.payload?.action
  return action === 'ingest_text' || action === 'ingest_file'
}

/** 从消息流提取环境仪表盘最新快照与 LLM 总结 */
/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function extractEnvDashboard(messages, agent) {
  const statusMsgs = messages
    .filter((m) => belongsToAgent(m, agent) && m.msg_type === 'system_status')
    .sort((a, b) => b.timestamp - a.timestamp)

  const latest = statusMsgs[0] || null
  const latestSnapshotMsg =
    statusMsgs.find((m) => m.message?.snapshot && m.message?.report_type !== 'summary') ||
    statusMsgs.find((m) => m.message?.snapshot) ||
    null
  const latestSummaryMsg =
    statusMsgs.find((m) => m.message?.report_type === 'summary' || m.message?.llm_summary?.summary) ||
    null

  const snapMsg = latestSnapshotMsg || latest
  const sumMsg = latestSummaryMsg || latest
  const alertMsg = snapMsg || latest

  return {
    snapshot: snapMsg?.message?.snapshot || null,
    snapshot_time: snapMsg?.timestamp || null,
    llm_summary: sumMsg?.message?.llm_summary || latest?.message?.llm_summary || null,
    summary_time: sumMsg?.timestamp || null,
    alert: alertMsg?.message?.alert === true,
    alert_reason: alertMsg?.message?.alert_reason || '',
    text: latest?.message?.text || '',
    updated_at: latest?.timestamp || snapMsg?.timestamp || null,
  }
}

export function makeUserMessageId() {
  return `user_ui_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

/** @param {string} targetAgentId */
export function buildUserTextMessage(targetAgentId, text, attachments = []) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text,
      role: 'user',
      ...(attachments.length ? { attachments } : {}),
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/** @param {string} targetAgentId */
export function buildScreenshotRequest(targetAgentId) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: '请求远程桌面截图',
      role: 'user',
      payload: { action: 'screenshot' },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/** @param {string} targetAgentId */
export function buildCameraRequest(targetAgentId) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: '请求摄像头拍照',
      role: 'user',
      payload: { action: 'camera' },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function securityPendingApprovals(messages, agent) {
  return messages
    .filter(
      (m) =>
        belongsToAgent(m, agent) &&
        m.msg_type === 'approval_request' &&
        m.status === 'pending',
    )
    .sort((a, b) => b.timestamp - a.timestamp)
}

/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function securityApprovalHistory(messages, agent) {
  return messages
    .filter(
      (m) =>
        belongsToAgent(m, agent) &&
        m.msg_type === 'approval_request' &&
        m.status &&
        m.status !== 'pending',
    )
    .sort((a, b) => b.timestamp - a.timestamp)
}

/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function securityYellowLogs(messages, agent) {
  return messages
    .filter((m) => belongsToAgent(m, agent) && m.msg_type === 'security_yellow_log')
    .sort((a, b) => b.timestamp - a.timestamp)
}

/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function securityChatMessages(messages, agent) {
  return messages.filter(
    (m) =>
      belongsToAgent(m, agent) &&
      m.msg_type === 'text' &&
      !m.message?.payload?.action,
  )
}

/** @param {string} targetAgentId */
export function buildSecurityAutoApproveAllMessage(targetAgentId) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: '请求模型自动审批全部待审批项',
      role: 'user',
      payload: { action: 'auto_approve', all: true },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/** @param {string} targetAgentId @param {string} approvalId */
export function buildSecurityAutoApproveMessage(targetAgentId, approvalId) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: '请求模型自动审批',
      role: 'user',
      payload: { action: 'auto_approve', approval_id: approvalId },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/** RAG 入库：文本内容（浏览器读文件后同样走此接口） */
/** @param {string} targetAgentId @param {{ text: string, title?: string, collection_id?: string, split_mode?: string }} opts */
export function buildRagIngestTextMessage(targetAgentId, opts) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  const title = opts.title || 'web_upload'
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: `入库文本: ${title}（${opts.text.length} 字）`,
      role: 'user',
      payload: {
        action: 'ingest_text',
        text: opts.text,
        title,
        collection_id: opts.collection_id || 'default',
        split_mode: opts.split_mode || 'rule',
      },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}
