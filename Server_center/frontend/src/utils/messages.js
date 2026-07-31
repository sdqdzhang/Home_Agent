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
  if (msg.msg_type === 'security_lists_result') {
    return msg.message?.ok ? '安全规则已更新' : '安全规则配置失败'
  }
  if (msg.msg_type === 'plan_result') return msg.message?.goal || msg.message?.summary || '任务规划'
  if (msg.msg_type === 'planning_session') {
    return msg.message?.text || msg.message?.goal || '任务规划'
  }
  if (msg.msg_type === 'clarify_request') return msg.message?.text || '规划质询'
  if (msg.msg_type === 'planning_action') return '规划操作'
  if (msg.msg_type === 'clarify_result') {
    return msg.message?.ready ? '信息已足够' : msg.message?.note || '质询'
  }
  if (msg.msg_type === 'env_probe_result') return '环境探测结果'
  if (msg.msg_type === 'plan_progress') {
    return `${msg.message?.node_id || '节点'} → ${msg.message?.status || ''}`
  }
  if (msg.msg_type === 'graph_run_result') {
    return msg.message?.ok ? '任务图执行完成' : msg.message?.error || '任务图执行失败'
  }
  if (msg.msg_type === 'datablock') {
    if (msg.message?.ok === false) return msg.message?.error || '处理失败'
    return msg.message?.output?.id || msg.message?.requirement || '处理结果'
  }
  if (msg.msg_type === 'memory_record') return msg.message?.key || '记忆写入'
  if (msg.msg_type === 'tool_result') return msg.message?.text || msg.message?.tool || '工具结果'
  if (msg.msg_type === 'cm_snapshot') return '会话管理快照'
  return `[${msg.msg_type}]`
}

/** @param {UiMessage} msg */
export function countsAsUnread(msg) {
  return (
    msg.msg_type !== 'system_status' &&
    msg.msg_type !== 'persona_state' &&
    msg.msg_type !== 'llm_config_result' &&
    msg.msg_type !== 'security_lists_result' &&
    msg.msg_type !== 'plan_progress' &&
    msg.msg_type !== 'clarify_result' &&
    msg.msg_type !== 'env_probe_result' &&
    msg.msg_type !== 'graph_run_result' &&
    msg.msg_type !== 'planning_action'
  )
}

/** 主对话中不单独展示的规划中间事件 */
const PLANNING_HIDDEN_TYPES = new Set([
  'plan_progress',
  'clarify_result',
  'env_probe_result',
  'graph_run_result',
  'planning_action',
])

/**
 * 折叠规划进度；优先展示 planning_session 单卡。
 * @param {UiMessage[]} messages
 * @returns {UiMessage[]}
 */
export function prepareChatMessages(messages) {
  if (!Array.isArray(messages) || !messages.length) return []

  /** @type {Record<string, Record<string, { status: string, attempts?: number, error?: string, detail?: string }>>} */
  const progressByReq = {}
  /** @type {Record<string, object>} */
  const finalNodeStatusByReq = {}
  /** @type {Record<string, UiMessage>} */
  const bestPlanByReq = {}
  /** @type {Set<string>} */
  const sessionReqIds = new Set()

  for (const msg of messages) {
    const rid = msg.message?.request_id
    if (!rid) continue

    if (msg.msg_type === 'planning_session') {
      sessionReqIds.add(rid)
      continue
    }

    if (msg.msg_type === 'plan_progress') {
      if (!progressByReq[rid]) progressByReq[rid] = {}
      const nid = msg.message?.node_id
      if (nid) {
        progressByReq[rid][nid] = {
          status: msg.message.status || 'pending',
          attempts: msg.message.attempts || 0,
          error: msg.message.status === 'failed' ? msg.message.detail || '' : '',
          detail: msg.message.detail || '',
        }
      }
      continue
    }

    if (msg.msg_type === 'graph_run_result' && msg.message?.node_status) {
      finalNodeStatusByReq[rid] = msg.message.node_status
      continue
    }

    if (msg.msg_type === 'plan_result') {
      const prev = bestPlanByReq[rid]
      const score = (m) => {
        let s = m.timestamp || 0
        if (m.message?.graph?.nodes?.length) s += 1e12
        if (['done', 'succeeded', 'failed', 'cancelled'].includes(m.message?.phase || m.message?.status)) {
          s += 1e11
        }
        return s
      }
      if (!prev || score(msg) >= score(prev)) {
        bestPlanByReq[rid] = msg
      }
    }
  }

  const usedPlanIds = new Set()
  const out = []

  for (const msg of messages) {
    if (PLANNING_HIDDEN_TYPES.has(msg.msg_type)) continue

    // 有 planning_session 时隐藏同 request 的旧 plan_result / clarify_request
    const rid = msg.message?.request_id
    if (rid && sessionReqIds.has(rid)) {
      if (msg.msg_type === 'plan_result' || msg.msg_type === 'clarify_request') continue
    }

    if (msg.msg_type === 'plan_result') {
      if (!rid) {
        out.push(msg)
        continue
      }
      const best = bestPlanByReq[rid]
      if (!best || best.id !== msg.id) continue
      if (usedPlanIds.has(rid)) continue
      usedPlanIds.add(rid)

      const live = progressByReq[rid] || {}
      const finals = finalNodeStatusByReq[rid] || {}
      const embedded = best.message?.node_status || {}
      const node_status = { ...embedded, ...live, ...finals }
      out.push({
        ...best,
        message: {
          ...best.message,
          node_status,
        },
      })
      continue
    }

    out.push(msg)
  }

  return out
}

/** @param {UiMessage[]} messages @param {{ id: string, names?: string[] }} agent */
export function hasPendingClarify(messages, agent) {
  return messages.some((m) => {
    if (!belongsToAgent(m, agent)) return false
    if (m.msg_type === 'clarify_request' && m.status === 'pending') return true
    if (
      m.msg_type === 'planning_session' &&
      (m.message?.phase === 'clarifying' || m.message?.status === 'clarifying') &&
      (m.message?.questions || []).length > 0
    ) {
      return true
    }
    return false
  })
}

/** 规划会话进行中（含收集/执行），用于禁用输入 */
export function hasActivePlanningSession(messages, agent) {
  return messages.some((m) => {
    if (!belongsToAgent(m, agent) || m.msg_type !== 'planning_session') return false
    const phase = m.message?.phase || m.message?.status
    return !['done', 'failed', 'cancelled', 'succeeded'].includes(phase)
  })
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
  if (recent.msg_type === 'plan_progress' && recent.message?.status === 'running') return true
  if (
    recent.msg_type === 'planning_session' &&
    !['done', 'failed', 'cancelled', 'succeeded'].includes(recent.message?.phase || recent.message?.status)
  ) {
    return true
  }
  if (recent.msg_type === 'plan_result' && ['running', 'collecting'].includes(recent.message?.phase || recent.message?.status)) {
    return true
  }
  if (recent.msg_type === 'clarify_request' && recent.status === 'pending') return true
  if (['execution_log', 'rag_result', 'datablock', 'plan_result', 'graph_run_result', 'planning_session'].includes(recent.msg_type) && age < 30) return true
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

/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function findRunningExecutorJob(messages, agent) {
  const logs = messages
    .filter(
      (m) =>
        belongsToAgent(m, agent) &&
        m.msg_type === 'execution_log' &&
        m.message?.status === 'running',
    )
    .sort((a, b) => b.timestamp - a.timestamp)
  const latest = logs[0]
  if (!latest) return null
  return {
    jobId: latest.message?.payload?.job_id || null,
    msg: latest,
  }
}

/** @param {string} targetAgentId @param {string | null} [jobId] */
export function buildExecutorCancelMessage(targetAgentId, jobId = null) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || '执行模块'
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: '终止当前执行',
      role: 'user',
      payload: {
        action: 'cancel',
        ...(jobId ? { job_id: jobId } : {}),
      },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

const KNOWN_EXECUTOR_MODES = new Set([
  'command',
  'read_file',
  'write_file',
  'delete_file',
  'browse_dir',
  'search_file',
  'search_content',
])

const ACTION_TYPE_TO_MODE = {
  'shell.run': 'command',
  'file.read': 'read_file',
  'file.write': 'write_file',
  'file.delete': 'delete_file',
  'dir.browse': 'browse_dir',
  'file.search': 'search_file',
  'content.search': 'search_content',
}

/** 执行模块子能力：从消息 payload 推断 mode（缺省视为未知/自动） */
/** @param {UiMessage} msg */
export function executorMessageMode(msg) {
  const payload = msg.message?.payload
  if (payload?.mode && KNOWN_EXECUTOR_MODES.has(payload.mode)) {
    return payload.mode
  }
  if (msg.msg_type === 'execution_log') {
    const actionType = payload?.result?.action_type || payload?.action_type
    if (actionType && ACTION_TYPE_TO_MODE[actionType]) {
      return ACTION_TYPE_TO_MODE[actionType]
    }
  }
  return null
}

/** 执行频道主区：该智能体的对话与执行日志（同 job_id 折叠为一条） */
/** @param {UiMessage[]} messages @param {{ id: string, names: string[] }} agent */
export function executorWorkspaceMessages(messages, agent) {
  const filtered = messages.filter(
    (m) =>
      belongsToAgent(m, agent) &&
      (m.msg_type === 'text' || m.msg_type === 'execution_log'),
  )
  return collapseExecutionLogsByJob(filtered)
}

/**
 * 同一 job_id 的 execution_log 只保留最新一条（兼容历史刷屏数据）。
 * @param {UiMessage[]} messages
 */
export function collapseExecutionLogsByJob(messages) {
  /** @type {Map<string, UiMessage>} */
  const bestByJob = new Map()
  /** @type {Array<{ kind: 'raw', msg: UiMessage } | { kind: 'job', jobId: string }>} */
  const slots = []

  for (const m of messages) {
    if (m.msg_type !== 'execution_log') {
      slots.push({ kind: 'raw', msg: m })
      continue
    }
    const jobId = m.message?.payload?.job_id
    if (!jobId) {
      slots.push({ kind: 'raw', msg: m })
      continue
    }
    const prev = bestByJob.get(jobId)
    if (!prev) {
      slots.push({ kind: 'job', jobId })
      bestByJob.set(jobId, m)
      continue
    }
    const prevDone = ['completed', 'failed', 'cancelled'].includes(prev.message?.status)
    const nextDone = ['completed', 'failed', 'cancelled'].includes(m.message?.status)
    if (nextDone || (!prevDone && (m.timestamp || 0) >= (prev.timestamp || 0))) {
      bestByJob.set(jobId, m)
    } else if ((m.timestamp || 0) > (prev.timestamp || 0)) {
      bestByJob.set(jobId, m)
    }
  }

  return slots.map((s) => (s.kind === 'job' ? bestByJob.get(s.jobId) : s.msg)).filter(Boolean)
}

/** 执行频道：附带独立 file_content 字段的用户消息（路径仍由模型从 text 解析） */
/** @param {string} targetAgentId @param {{ content: string, instruction: string, mode?: string | null }} opts */
export function buildExecutorMessageWithBody(targetAgentId, { content, instruction, mode = null }) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || '执行模块'
  const text = instruction?.trim() || '将侧栏正文写入指定文件'
  /** @type {Record<string, unknown>} */
  const payload = { file_content: content }
  if (mode) payload.mode = mode
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text,
      role: 'user',
      payload,
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/** @param {string} targetAgentId @param {Record<string, unknown>} [extraPayload] */
export function buildUserTextMessage(targetAgentId, text, attachments = [], extraPayload = null) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || targetAgentId
  const displayAttachments = attachments.map(({ name, size }) => ({ name, size }))
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text,
      role: 'user',
      ...(displayAttachments.length ? { attachments: displayAttachments } : {}),
      ...(extraPayload ? { payload: extraPayload } : {}),
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
