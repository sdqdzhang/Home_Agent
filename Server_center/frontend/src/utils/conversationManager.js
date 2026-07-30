import { belongsToAgent, sortMessagesAsc } from './messages.js'

/**
 * @param {import('./messages.js').UiMessage[]} messages
 * @param {import('../config/agents.js').Agent} agent
 */
export function conversationManagerMessages(messages, agent) {
  return sortMessagesAsc(messages.filter((m) => belongsToAgent(m, agent)))
}

/**
 * Latest cm_snapshot payload, or null.
 * @param {import('./messages.js').UiMessage[]} messages
 * @param {import('../config/agents.js').Agent} agent
 */
export function latestSnapshot(messages, agent) {
  const rows = conversationManagerMessages(messages, agent)
  for (let i = rows.length - 1; i >= 0; i -= 1) {
    const m = rows[i]
    if (m.msg_type === 'cm_snapshot' && m.message && typeof m.message === 'object') {
      return m.message
    }
  }
  return null
}
