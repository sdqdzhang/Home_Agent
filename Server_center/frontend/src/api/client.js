import { WS_TARGET } from '../config/agents.js'

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

export async function fetchMessages({ target = WS_TARGET, name = null, limit = 200 } = {}) {
  const params = new URLSearchParams({ target, limit: String(limit) })
  if (name) params.set('name', name)
  const res = await fetch(`/api/v1/messages?${params}`)
  if (!res.ok) throw new Error(`加载消息失败: ${res.status}`)
  const data = await res.json()
  return data.messages || []
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

export { WS_TARGET }
