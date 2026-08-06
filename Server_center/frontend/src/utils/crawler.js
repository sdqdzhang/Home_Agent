import { findAgentByName, USER_SENDER } from '../config/agents.js'
import { belongsToAgent, makeUserMessageId } from './messages.js'
import { sendMessageLocal } from '../api/client.js'

export const CRAWL_MSG_TYPE = 'execution_log'

/**
 * @param {string} targetAgentId
 * @param {{ url: string, task?: string, config?: object, use_model?: boolean, request_id: string }} opts
 */
export function buildCrawlMessage(targetAgentId, { url, task = '', config = {}, use_model = true, request_id }) {
  const agent = findAgentByName(targetAgentId)
  const target = agent?.names[0] || '网页爬取模块'
  const trimmedUrl = String(url || '').trim()
  const trimmedTask = String(task || '').trim()
  return {
    id: makeUserMessageId(),
    name: USER_SENDER,
    target,
    msg_type: 'text',
    message: {
      text: trimmedTask || `爬取 ${trimmedUrl}`,
      role: 'user',
      payload: {
        url: trimmedUrl,
        task: trimmedTask,
        config: config && typeof config === 'object' ? config : {},
        use_model: Boolean(use_model),
        request_id,
      },
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
}

/**
 * @param {import('./messages.js').UiMessage} msg
 */
export function crawlResultFromMessage(msg) {
  if (!msg || msg.msg_type !== CRAWL_MSG_TYPE) return null
  const status = msg.message?.status
  if (status === 'running') return null
  const result = msg.message?.payload?.result
  return {
    requestId: msg.message?.request_id || '',
    jobId: msg.message?.payload?.job_id || result?.job_id || '',
    status,
    summary: msg.message?.summary || '',
    log: Array.isArray(msg.message?.log) ? msg.message.log : [],
    result: result && typeof result === 'object' ? result : null,
    success: Boolean(result?.success ?? (status === 'completed')),
    timestamp: msg.timestamp,
    messageId: msg.id,
  }
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} requestId
 * @param {number} [timeoutMs]
 */
export function waitForCrawlResult(getMessages, requestId, timeoutMs = 300000) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + timeoutMs

    const tick = () => {
      const hit = getMessages().find((m) => {
        if (m.msg_type !== CRAWL_MSG_TYPE) return false
        if (m.message?.request_id !== requestId) return false
        const status = m.message?.status
        return status === 'completed' || status === 'failed'
      })
      if (hit) {
        resolve(crawlResultFromMessage(hit))
        return
      }
      if (Date.now() > deadline) {
        reject(new Error('爬取超时：请确认 Local Agent 已启动并已连接 Server Center'))
        return
      }
      setTimeout(tick, 250)
    }

    tick()
  })
}

/**
 * @param {() => import('./messages.js').UiMessage[]} getMessages
 * @param {string} targetAgentId
 * @param {{ url: string, task?: string, config?: object, use_model?: boolean }} opts
 * @param {{ onSent?: (msg: import('./messages.js').UiMessage) => void }} [hooks]
 */
export async function requestCrawl(getMessages, targetAgentId, opts, hooks = {}) {
  const requestId = crypto.randomUUID()
  const msg = buildCrawlMessage(targetAgentId, {
    url: opts.url,
    task: opts.task,
    config: opts.config,
    use_model: opts.use_model,
    request_id: requestId,
  })
  const pending = waitForCrawlResult(getMessages, requestId)
  const result = await sendMessageLocal(msg)
  if (result?.message) {
    hooks.onSent?.(result.message)
  }
  return pending
}

/**
 * 近期爬取任务：同一次请求只保留一条（完成态优先于 running）。
 * @param {import('./messages.js').UiMessage[]} messages
 * @param {{ id: string, names: string[] }} agent
 * @param {number} [limit]
 */
export function crawlerJobMessages(messages, agent, limit = 40) {
  const all = messages
    .filter((m) => belongsToAgent(m, agent) && m.msg_type === CRAWL_MSG_TYPE)
    .sort((a, b) => b.timestamp - a.timestamp)

  /** @type {Map<string, import('./messages.js').UiMessage>} */
  const byKey = new Map()
  /** @type {import('./messages.js').UiMessage[]} */
  const orphan = []

  for (const m of all) {
    const requestId = String(m.message?.request_id || '').trim()
    const jobId = String(m.message?.payload?.job_id || m.message?.payload?.result?.job_id || '').trim()
    const key = requestId ? `r:${requestId}` : jobId ? `j:${jobId}` : ''
    if (!key) {
      orphan.push(m)
      continue
    }
    const prev = byKey.get(key)
    if (!prev) {
      byKey.set(key, m)
      continue
    }
    // 已有终态则忽略更早的 running；终态互相取更新时间（列表已按时间降序）
    const prevDone = prev.message?.status === 'completed' || prev.message?.status === 'failed'
    const curDone = m.message?.status === 'completed' || m.message?.status === 'failed'
    if (!prevDone && curDone) {
      byKey.set(key, m)
    }
  }

  return [...byKey.values(), ...orphan]
    .sort((a, b) => b.timestamp - a.timestamp)
    .slice(0, limit)
}

/**
 * @param {object|null|undefined} result
 */
export function buildCrawlFileText(result) {
  if (!result || typeof result !== 'object') return ''
  const title = String(result.title || '').trim()
  const url = String(result.url || '').trim()
  const content = String(result.content || '').trim()
  const strategy = String(result.strategy || '').trim()
  const picked = String(result.picked_filter || '').trim()
  const lines = []
  if (title) lines.push(`# ${title}`)
  if (url) lines.push(`来源: ${url}`)
  if (strategy || picked) {
    const meta = [strategy && `引擎 ${strategy}`, picked && `过滤 ${picked}`].filter(Boolean).join(' · ')
    if (meta) lines.push(meta)
  }
  if (lines.length) lines.push('')
  lines.push(content)
  return lines.join('\n').trim() + (content ? '\n' : '')
}

/**
 * @param {object|null|undefined} result
 */
export function suggestCrawlFilename(result) {
  const rawTitle = String(result?.title || '').trim()
  let base = ''
  if (rawTitle) {
    base = rawTitle
  } else {
    try {
      base = new URL(String(result?.url || '')).hostname || 'crawl'
    } catch {
      base = 'crawl'
    }
  }
  base = base
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, '_')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^[._]+|[._]+$/g, '')
    .slice(0, 60)
  if (!base) base = 'crawl'
  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  return `${base}_${stamp}.md`
}

/**
 * 浏览器下载过滤后正文为本地文件。
 * @param {string} text
 * @param {string} filename
 */
export function downloadTextFile(text, filename) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename || 'crawl.md'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(href)
}
