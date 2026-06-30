<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { fetchTerminalStatus } from '../api/client.js'
import '@xterm/xterm/css/xterm.css'

const props = defineProps({
  agent: { type: Object, required: true },
  active: { type: Boolean, default: true },
})

const emit = defineEmits(['error'])

const containerRef = ref(null)
const status = ref({ enabled: true, agent_connected: false })
const connected = ref(false)
const statusText = ref('正在连接…')

let term = null
let fitAddon = null
let ws = null
let resizeObserver = null
let resizeTimer = null
let connectGen = 0

function wsUrl() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  // 开发模式直连 Server Center，hostname 与页面一致（避免 localhost/127.0.0.1 混用）
  const host = import.meta.env.DEV ? `${location.hostname}:8765` : location.host
  return `${protocol}//${host}/ws/terminal`
}

function sendResize() {
  if (!ws || ws.readyState !== WebSocket.OPEN || !term) return
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN || !term) return
    ws.send(
      JSON.stringify({
        type: 'resize',
        cols: term.cols,
        rows: term.rows,
      }),
    )
  }, 80)
}

function resetTerminalScreen() {
  if (!term) return
  term.reset()
}

function connectTerminal() {
  const gen = ++connectGen
  disconnectTerminal(false)
  if (!props.active) return

  resetTerminalScreen()
  statusText.value = '正在连接终端…'
  const socket = new WebSocket(wsUrl())
  ws = socket
  socket.binaryType = 'arraybuffer'

  socket.onopen = () => {
    if (gen !== connectGen || ws !== socket) return
    connected.value = true
    statusText.value = '已连接'
    if (fitAddon && term) fitAddon.fit()
    sendResize()
  }

  socket.onclose = (event) => {
    if (gen !== connectGen) return
    connected.value = false
    if (event.code === 1008) {
      statusText.value = '终端功能已关闭'
    } else if (!event.wasClean && event.code !== 1000) {
      statusText.value = `连接已断开 (${event.code || 'unknown'})`
    } else {
      statusText.value = '连接已断开'
    }
  }

  socket.onerror = () => {
    if (gen !== connectGen || connected.value) return
    statusText.value = 'WebSocket 连接失败，请确认 Server Center 已启动'
    emit('error', '终端 WebSocket 连接失败')
  }

  socket.onmessage = (event) => {
    if (!term || ws !== socket) return
    if (event.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(event.data))
      return
    }
    try {
      const payload = JSON.parse(event.data)
      if (payload.type === 'error') {
        term.writeln(`\r\n\x1b[31m${payload.message}\x1b[0m`)
        statusText.value = payload.message
        emit('error', payload.message)
        return
      }
      if (payload.type === 'agent_disconnected') {
        term.writeln('\r\n\x1b[33mLocal Agent 已断开\x1b[0m')
        statusText.value = 'Local Agent 未连接'
        return
      }
      if (payload.type === 'session_ready') {
        statusText.value = '会话已就绪'
        resetTerminalScreen()
      }
    } catch {
      term.write(event.data)
    }
  }
}

function disconnectTerminal(incrementGen = true) {
  if (incrementGen) connectGen += 1
  if (resizeTimer) {
    clearTimeout(resizeTimer)
    resizeTimer = null
  }
  if (ws) {
    ws.onopen = null
    ws.onclose = null
    ws.onerror = null
    ws.onmessage = null
    ws.close()
    ws = null
  }
  connected.value = false
}

function initTerminal() {
  if (!containerRef.value || term) return
  term = new Terminal({
    cursorBlink: true,
    fontSize: 14,
    fontFamily: 'Consolas, "Courier New", monospace',
    theme: {
      background: '#0f1419',
      foreground: '#e2e8f0',
      cursor: '#34d399',
    },
  })
  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(containerRef.value)
  fitAddon.fit()

  term.onData((data) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  })

  resizeObserver = new ResizeObserver(() => {
    if (!fitAddon || !term) return
    fitAddon.fit()
    sendResize()
  })
  resizeObserver.observe(containerRef.value)
}

async function refreshStatus() {
  try {
    status.value = await fetchTerminalStatus()
  } catch (e) {
    emit('error', e.message)
  }
}

onMounted(async () => {
  await refreshStatus()
  initTerminal()
  // 等 DOM / xterm 就绪后再连，避免首帧 resize 洪泛
  requestAnimationFrame(() => connectTerminal())
})

onUnmounted(() => {
  disconnectTerminal()
  resizeObserver?.disconnect()
  term?.dispose()
  term = null
  fitAddon = null
})
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div class="flex shrink-0 items-center justify-between border-b border-surface-border bg-surface-raised/60 px-4 py-2">
      <div class="min-w-0">
        <p class="text-sm font-medium text-slate-200">远程终端</p>
        <p class="text-[11px] text-slate-500">
          直连本机 cmd，不经 AI 执行模块与安全检查
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-3 text-[11px]">
        <span :class="status.enabled ? 'text-emerald-400' : 'text-amber-400'">
          {{ status.enabled ? '功能已开启' : '功能已关闭' }}
        </span>
        <span :class="status.agent_connected ? 'text-emerald-400' : 'text-slate-500'">
          Agent {{ status.agent_connected ? '在线' : '离线' }}
        </span>
        <span :class="connected ? 'text-emerald-400' : 'text-slate-500'">{{ statusText }}</span>
        <button
          type="button"
          class="rounded border border-surface-border px-2 py-1 text-slate-300 hover:bg-white/5"
          @click="connectTerminal"
        >
          重连
        </button>
      </div>
    </div>

    <div
      ref="containerRef"
      class="min-h-0 flex-1 overflow-hidden bg-[#0f1419] p-1"
    />
  </div>
</template>
