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
  if (msg.msg_type === 'execution_log') return msg.message?.summary || '执行日志'
  if (msg.msg_type === 'system_status') return msg.message?.text || '系统状态更新'
  if (msg.msg_type === 'persona_state') return msg.message?.mood || '状态更新'
  if (msg.msg_type === 'rag_result') return msg.message?.query || 'RAG 检索结果'
  if (msg.msg_type === 'reflection_note') return msg.message?.issue || '自省记录'
  if (msg.msg_type === 'memory_record') return msg.message?.key || '记忆写入'
  return `[${msg.msg_type}]`
}

/** @param {UiMessage} msg */
export function countsAsUnread(msg) {
  return msg.msg_type !== 'system_status' && msg.msg_type !== 'persona_state'
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
