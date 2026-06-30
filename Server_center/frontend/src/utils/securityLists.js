import { findAgentByName, USER_SENDER } from '../config/agents.js'
import { makeUserMessageId } from './messages.js'
import { sendMessageLocal } from '../api/client.js'

export const SECURITY_LISTS_MSG_TYPE = 'security_lists_result'

const SECURITY_AGENT_ID = 'security'

const TAB_LABELS = {
  white_commands: '白命令',
  black_commands: '黑命令',
  white_directories: '白目录',
  black_directories: '黑目录',
}

export const SECURITY_LIST_TABS = Object.entries(TAB_LABELS).map(([key, label]) => ({
  key,
  label,
}))

/** @param {Record<string, unknown>} payload */
export function buildSecurityListsMessage(payload) {
  const agent = findAgentByName(SECURITY_AGENT_ID)
  const target = agent?.names[0] || '安全检查模块'
  const action = String(payload.action || 'security_lists_get')
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: `安全规则: ${action}`,
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
export function waitForSecurityListsResult(getMessages, requestId, timeoutMs = 12000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs

    const tick = () => {
      const hit = getMessages().find(
        (m) =>
          m.msg_type === SECURITY_LISTS_MSG_TYPE &&
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
export async function requestSecurityLists(getMessages, payload) {
  const requestId = crypto.randomUUID()
  const msg = buildSecurityListsMessage({ ...payload, request_id: requestId })
  const pending = waitForSecurityListsResult(getMessages, requestId)
  await sendMessageLocal(msg)
  const body = await pending
  if (!body.ok) {
    const err = body.error || {}
    const detail = err.message || '规则配置操作失败'
    const e = new Error(detail)
    e.code = err.code
    throw e
  }
  return body.data
}

/** @param {string} code @param {string} [fallback] */
export function securityListsErrorText(code, fallback) {
  if (code === 'invalid_request') return fallback || '请求参数无效'
  return fallback || '操作失败'
}
