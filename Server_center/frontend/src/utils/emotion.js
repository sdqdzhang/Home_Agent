import { findAgentByName, USER_SENDER } from '../config/agents.js'
import { belongsToAgent, makeUserMessageId, sortMessagesAsc } from './messages.js'
import { sendMessageLocal } from '../api/client.js'

export const MIND_SNAPSHOT_MSG_TYPE = 'mind_snapshot'
const EMOTION_AGENT_ID = 'emotion'

/**
 * @param {import('./messages.js').UiMessage[]} messages
 * @param {import('../config/agents.js').Agent} agent
 */
export function emotionMessages(messages, agent) {
  return sortMessagesAsc(messages.filter((m) => belongsToAgent(m, agent)))
}

/**
 * @param {import('./messages.js').UiMessage[]} messages
 * @param {import('../config/agents.js').Agent} agent
 */
export function latestMindSnapshot(messages, agent) {
  const rows = emotionMessages(messages, agent)
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const m = rows[i]
    if (m.msg_type === MIND_SNAPSHOT_MSG_TYPE && m.message && typeof m.message === 'object') {
      return m.message
    }
  }
  return null
}

/** @param {Record<string, unknown>} payload */
export function buildEmotionActionMessage(payload) {
  const agent = findAgentByName(EMOTION_AGENT_ID)
  const target = agent?.names[0] || '情感与性格状态模块'
  const action = String(payload.action || 'refresh')
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: `Mind: ${action}`,
      role: 'user',
      payload,
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} requestId
 * @param {number} [timeoutMs]
 */
export function waitForMindSnapshot(getMessages, requestId, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs
    const tick = () => {
      const hit = getMessages().find(
        (m) =>
          m.msg_type === MIND_SNAPSHOT_MSG_TYPE &&
          m.message?.request_id === requestId,
      )
      if (hit) {
        resolve(hit.message)
        return
      }
      if (Date.now() > deadline) {
        reject(new Error('Local Agent 无响应，请确认 Agent 已启动并已连接 Server Center'))
        return
      }
      setTimeout(tick, 120)
    }
    tick()
  })
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {Record<string, unknown>} payload
 */
export async function requestEmotionAction(getMessages, payload) {
  const requestId = crypto.randomUUID()
  const msg = buildEmotionActionMessage({ ...payload, request_id: requestId })
  const pending = waitForMindSnapshot(getMessages, requestId)
  await sendMessageLocal(msg)
  return pending
}

/** @param {Record<string, unknown>|null|undefined} persona */
export function personaSummaryLines(persona) {
  if (!persona || typeof persona !== 'object') return []
  const summary = String(persona.summary || '').trim()
  return summary ? summary.split(/\n+/).map((s) => s.trim()).filter(Boolean) : []
}
