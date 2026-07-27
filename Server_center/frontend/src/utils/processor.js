import { findAgentByName, USER_SENDER } from '../config/agents.js'
import { makeUserMessageId } from './messages.js'
import { sendMessageLocal } from '../api/client.js'

export const DATABLOCK_MSG_TYPE = 'datablock'
export const UI_BLOCK_ID_PREFIX = 'ui'

/**
 * @param {string} targetAgentId
 * @param {{ requirement: string, blocks: object[], request_id: string }} opts
 */
export function buildProcessorMessage(targetAgentId, { requirement, blocks, request_id }) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || '处理'
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: requirement,
      role: 'user',
      requirement,
      payload: {
        requirement,
        blocks,
        request_id,
      },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} requestId
 * @param {number} [timeoutMs]
 */
export function waitForProcessorResult(getMessages, requestId, timeoutMs = 180000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs

    const tick = () => {
      const hit = getMessages().find(
        (m) =>
          m.msg_type === DATABLOCK_MSG_TYPE &&
          m.message?.request_id === requestId,
      )
      if (hit) {
        resolve(hit.message)
        return
      }
      if (Date.now() > deadline) {
        reject(new Error('处理超时：请确认 Local Agent 已启动并已连接 Server Center'))
        return
      }
      setTimeout(tick, 200)
    }

    tick()
  })
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} targetAgentId
 * @param {{ requirement: string, blocks: object[] }} opts
 */
export async function requestProcessor(getMessages, targetAgentId, opts) {
  const requestId = crypto.randomUUID()
  const msg = buildProcessorMessage(targetAgentId, {
    requirement: opts.requirement,
    blocks: opts.blocks,
    request_id: requestId,
  })
  const pending = waitForProcessorResult(getMessages, requestId)
  await sendMessageLocal(msg)
  return pending
}
