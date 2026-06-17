import { findAgentByName, USER_SENDER } from '../config/agents.js'
import { makeUserMessageId } from './messages.js'
import { sendMessageLocal } from '../api/client.js'

export const LLM_CONFIG_MSG_TYPE = 'llm_config_result'

const LLM_AGENT_ID = 'llm'

/** @param {Record<string, unknown>} payload */
export function buildLlmConfigMessage(payload) {
  const agent = findAgentByName(LLM_AGENT_ID)
  const target = agent?.names[0] || '本地Agent'
  const action = String(payload.action || 'llm_config_list')
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: `LLM配置: ${action}`,
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
export function waitForLlmConfigResult(getMessages, requestId, timeoutMs = 12000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs

    const tick = () => {
      const hit = getMessages().find(
        (m) =>
          m.msg_type === LLM_CONFIG_MSG_TYPE &&
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
export async function requestLlmConfig(getMessages, payload) {
  const requestId = crypto.randomUUID()
  const msg = buildLlmConfigMessage({ ...payload, request_id: requestId })
  const pending = waitForLlmConfigResult(getMessages, requestId)
  await sendMessageLocal(msg)
  const body = await pending
  if (!body.ok) {
    const err = body.error || {}
    const detail = err.message || '配置操作失败'
    const e = new Error(detail)
    e.code = err.code
    e.slotKeys = err.slot_keys
    throw e
  }
  return body.data
}

/** @param {string} code @param {string} [fallback] */
export function llmConfigErrorText(code, fallback) {
  if (code === 'endpoint_in_use') {
    return fallback || '该模型仍被槽位引用，请先在下方改绑后再删除'
  }
  if (code === 'invalid_request') return fallback || '请求参数无效'
  return fallback || '操作失败'
}
