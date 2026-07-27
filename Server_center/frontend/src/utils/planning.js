import { findAgentByName, USER_SENDER } from '../config/agents.js'
import { makeUserMessageId } from './messages.js'
import { sendMessageLocal } from '../api/client.js'

export const PLANNING_REQUEST = 'planning_request'
export const CLARIFY_RESULT = 'clarify_result'
export const ENV_PROBE_RESULT = 'env_probe_result'
export const PLAN_RESULT = 'plan_result'
export const PLAN_PROGRESS = 'plan_progress'
export const GRAPH_RUN_RESULT = 'graph_run_result'

export const OTHER_LABEL = '其他（自行输入）'
export const MAX_COLLECT_ROUNDS = 8

/**
 * @param {string} targetAgentId
 * @param {string} action
 * @param {object} payload
 */
export function buildPlanningMessage(targetAgentId, action, payload) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || '规划模块'
  const request_id = payload.request_id || crypto.randomUUID()
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: PLANNING_REQUEST,
    message: {
      text: payload.text || `[planning:${action}]`,
      role: 'user',
      action,
      request_id,
      payload: { ...payload, action, request_id },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} msgType
 * @param {string} requestId
 * @param {number} [timeoutMs]
 */
export function waitForPlanningResult(getMessages, msgType, requestId, timeoutMs = 300000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs
    const tick = () => {
      const hit = getMessages().find(
        (m) => m.msg_type === msgType && m.message?.request_id === requestId,
      )
      if (hit) {
        resolve(hit.message)
        return
      }
      if (Date.now() > deadline) {
        reject(new Error('规划超时：请确认 Local Agent 已启动并已连接 Server Center'))
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
 * @param {object} opts
 */
export async function requestClarify(getMessages, targetAgentId, opts) {
  const request_id = crypto.randomUUID()
  const msg = buildPlanningMessage(targetAgentId, 'clarify', {
    request_id,
    goal: opts.goal,
    history: opts.history || [],
    env_records: opts.env_records || [],
    round_index: opts.round_index || 1,
    text: `信息收集 第 ${opts.round_index || 1} 轮`,
  })
  const pending = waitForPlanningResult(getMessages, CLARIFY_RESULT, request_id)
  await sendMessageLocal(msg)
  return pending
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} targetAgentId
 * @param {{ queries: object[], round_index: number }} opts
 */
export async function requestEnvProbe(getMessages, targetAgentId, opts) {
  const request_id = crypto.randomUUID()
  const msg = buildPlanningMessage(targetAgentId, 'env_probe', {
    request_id,
    queries: opts.queries,
    round_index: opts.round_index || 1,
    text: `环境探测 ${opts.queries?.length || 0} 条`,
  })
  const pending = waitForPlanningResult(getMessages, ENV_PROBE_RESULT, request_id, 600000)
  await sendMessageLocal(msg)
  return pending
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} targetAgentId
 * @param {object} opts
 */
export async function requestPlan(getMessages, targetAgentId, opts) {
  const request_id = crypto.randomUUID()
  const msg = buildPlanningMessage(targetAgentId, 'plan', {
    request_id,
    goal: opts.goal,
    clarifications: opts.clarifications || opts.history || [],
    context_blocks: opts.context_blocks || [],
    text: '生成任务图',
  })
  const pending = waitForPlanningResult(getMessages, PLAN_RESULT, request_id)
  await sendMessageLocal(msg)
  return pending
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} targetAgentId
 * @param {object} opts
 */
export async function requestRunGraph(getMessages, targetAgentId, opts) {
  const request_id = opts.request_id || crypto.randomUUID()
  const msg = buildPlanningMessage(targetAgentId, 'run_graph', {
    request_id,
    goal: opts.goal,
    graph: opts.graph,
    initial_blocks: opts.initial_blocks || [],
    text: '执行任务图',
  })
  const pending = waitForPlanningResult(getMessages, GRAPH_RUN_RESULT, request_id, 900000)
  await sendMessageLocal(msg)
  return { request_id, resultPromise: pending }
}

/**
 * @param {object[]} clarifications
 * @param {string} goal
 */
export function composeGoal(goal, clarifications) {
  const base = String(goal || '').trim()
  const items = (clarifications || []).filter((c) => String(c.answer || '').trim())
  if (!items.length) return base
  const lines = [base, '', '## 澄清补充']
  for (const c of items) {
    const label = String(c.question || c.question_id || '').trim()
    const answer = String(c.answer).trim()
    lines.push(label ? `- ${label}：${answer}` : `- ${answer}`)
  }
  return lines.join('\n')
}
