import { USER_SENDER, WS_TARGET } from '../config/agents.js'

export async function fetchModules() {
  const res = await fetch('/api/v1/modules')
  if (!res.ok) throw new Error(`加载模块列表失败: ${res.status}`)
  return res.json()
}

export async function fetchHealth() {
  const res = await fetch('/health')
  if (!res.ok) throw new Error('health check failed')
  return res.json()
}

export async function fetchTerminalStatus() {
  const res = await fetch('/api/v1/terminal/status')
  if (!res.ok) throw new Error(`加载终端状态失败: ${res.status}`)
  return res.json()
}

export async function fetchMessages({ target, name = null, limit = 200 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) })
  // target 未传时默认只拉发往 user_ui 的模块消息；显式传 null 表示不按 target 过滤
  if (target === undefined) target = WS_TARGET
  if (target) params.set('target', target)
  if (name) params.set('name', name)
  const res = await fetch(`/api/v1/messages?${params}`)
  if (!res.ok) throw new Error(`加载消息失败: ${res.status}`)
  const data = await res.json()
  return data.messages || []
}

/** 加载双向聊天记录：模块回复 + 用户发出 */
export async function fetchChatMessages(limit = 300) {
  const [inbound, outbound] = await Promise.all([
    fetchMessages({ target: WS_TARGET, limit }),
    // 用户消息 name=user_ui、target=各模块；必须清空默认 target，否则会变成 name+target 双过滤而查不到
    fetchMessages({ target: null, name: USER_SENDER, limit }),
  ])
  const byId = new Map()
  for (const msg of [...inbound, ...outbound]) {
    if (msg?.id) byId.set(msg.id, msg)
  }
  return [...byId.values()]
}

export async function sendMessageLocal(msg) {
  const res = await fetch('/api/v1/messages/local', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(msg),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `发送失败: ${res.status}`)
  }
  return res.json()
}

export async function respondMessage(messageId, approved, reason = '') {
  const body = {
    ref_id: messageId,
    msg_type: 'approval_response',
    message: { approved, reason },
    timestamp: Math.floor(Date.now() / 1000),
  }
  const res = await fetch(`/api/v1/messages/${messageId}/respond/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `审批失败: ${res.status}`)
  }
  return res.json()
}

/** 规划质询卡片提交 */
export async function respondClarify(messageId, payload) {
  const body = {
    ref_id: messageId,
    msg_type: 'clarify_response',
    message: payload,
    timestamp: Math.floor(Date.now() / 1000),
  }
  const res = await fetch(`/api/v1/messages/${messageId}/respond/local`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `提交质询失败: ${res.status}`)
  }
  return res.json()
}

export function connectWebSocket(target, handlers) {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${protocol}//${location.host}/ws/${target}`)
  ws.onopen = () => handlers.onOpen?.()
  ws.onclose = () => handlers.onClose?.()
  ws.onerror = (e) => handlers.onError?.(e)
  ws.onmessage = (event) => {
    try {
      handlers.onMessage?.(JSON.parse(event.data))
    } catch {
      /* ignore */
    }
  }
  return ws
}

export { USER_SENDER, WS_TARGET }
