<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { AGENTS } from './config/agents.js'
import { connectWebSocket, fetchHealth, fetchMessages, sendMessageLocal, WS_TARGET } from './api/client.js'
import AgentSidebar from './components/AgentSidebar.vue'
import ChatHeader from './components/ChatHeader.vue'
import ChatInput from './components/ChatInput.vue'
import EnvWorkspace from './components/EnvWorkspace.vue'
import MessageList from './components/MessageList.vue'
import {
  agentMood,
  belongsToAgent,
  buildUserTextMessage,
  buildScreenshotRequest,
  buildCameraRequest,
  globalEmotionMood,
  sortMessagesAsc,
} from './utils/messages.js'

const agents = AGENTS
const allMessages = ref([])
const selectedAgentId = ref('jarvis')
const mobileView = ref('list')
const loading = ref(true)
const wsConnected = ref(false)
const healthy = ref(true)
const error = ref('')
const lastReadAt = ref(Object.fromEntries(agents.map((a) => [a.id, 0])))

/** WebSocket 只订阅 user_ui；服务端会向 target + channel 双播，多订频道无必要 */
const WS_CHANNELS = [WS_TARGET]

let wsSockets = []
let healthTimer = null
let pollTimer = null

const selectedAgent = computed(() => agents.find((a) => a.id === selectedAgentId.value) || agents[0])

const chatMessages = computed(() =>
  sortMessagesAsc(allMessages.value.filter((m) => belongsToAgent(m, selectedAgent.value))),
)

const currentMood = computed(() => agentMood(allMessages.value, selectedAgent.value))
const globalMood = computed(() => globalEmotionMood(allMessages.value))

function upsertMessage(item) {
  if (!item?.id) return
  const idx = allMessages.value.findIndex((m) => m.id === item.id)
  if (idx >= 0) {
    const next = [...allMessages.value]
    next[idx] = { ...item, channel: item.channel || next[idx].channel }
    allMessages.value = next
  } else {
    allMessages.value = [...allMessages.value, item]
  }
}

function mergeMessages(incoming) {
  if (!Array.isArray(incoming)) return
  for (const msg of incoming) upsertMessage(msg)
}

function markAgentRead(agentId) {
  lastReadAt.value[agentId] = Math.floor(Date.now() / 1000)
}

function selectAgent(agentId) {
  selectedAgentId.value = agentId
  markAgentRead(agentId)
  mobileView.value = 'chat'
}

function backToList() {
  mobileView.value = 'list'
}

async function loadMessages() {
  loading.value = true
  error.value = ''
  try {
    const msgs = await fetchMessages({ target: WS_TARGET, limit: 300 })
    allMessages.value = msgs
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function refreshMessagesQuiet() {
  try {
    const msgs = await fetchMessages({ target: WS_TARGET, limit: 300 })
    mergeMessages(msgs)
  } catch {
    /* 静默轮询失败不打断 UI */
  }
}

async function checkHealth() {
  try {
    await fetchHealth()
    healthy.value = true
  } catch {
    healthy.value = false
  }
}

function handleWsMessage(payload) {
  if (payload.event === 'new_message' || payload.event === 'message_updated') {
    upsertMessage(payload.data)
  }
}

function connectAll() {
  wsSockets.forEach((ws) => ws?.close())
  wsSockets = []

  const openChannels = new Set()

  const handleClose = (channel) => {
    openChannels.delete(channel)
    wsConnected.value = openChannels.size > 0
    if (openChannels.size === 0) {
      setTimeout(connectAll, 3000)
    }
  }

  for (const channel of WS_CHANNELS) {
    const ws = connectWebSocket(channel, {
      onOpen: () => {
        openChannels.add(channel)
        wsConnected.value = true
      },
      onClose: () => handleClose(channel),
      onMessage: handleWsMessage,
    })
    wsSockets.push(ws)
  }
}

async function onSend(text, attachments) {
  error.value = ''
  try {
    const msg = buildUserTextMessage(selectedAgentId.value, text, attachments)
    const result = await sendMessageLocal(msg)
    upsertMessage(result.message)
  } catch (e) {
    error.value = e.message
  }
}

async function requestScreenshot() {
  error.value = ''
  try {
    const msg = buildScreenshotRequest('env')
    const result = await sendMessageLocal(msg)
    upsertMessage(result.message)
  } catch (e) {
    error.value = e.message
  }
}

async function requestCamera() {
  error.value = ''
  try {
    const msg = buildCameraRequest('env')
    const result = await sendMessageLocal(msg)
    upsertMessage(result.message)
  } catch (e) {
    error.value = e.message
  }
}

function onResponded(msg) {
  upsertMessage(msg)
}

watch(selectedAgentId, (id) => {
  if (mobileView.value === 'chat') markAgentRead(id)
})

watch(selectedAgentId, (id) => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (id === 'env') {
    pollTimer = setInterval(refreshMessagesQuiet, 8000)
  }
})

onMounted(async () => {
  await loadMessages()
  connectAll()
  await checkHealth()
  healthTimer = setInterval(checkHealth, 30000)
})

onUnmounted(() => {
  wsSockets.forEach((ws) => ws?.close())
  wsSockets = []
  if (healthTimer) clearInterval(healthTimer)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="flex h-full w-full overflow-hidden">
    <div
      class="h-full shrink-0 transition-panel duration-300 ease-out md:relative md:block md:w-sidebar"
      :class="
        mobileView === 'list'
          ? 'fixed inset-0 z-20 w-full md:static'
          : 'pointer-events-none fixed inset-0 z-0 w-full -translate-x-full opacity-0 md:pointer-events-auto md:static md:translate-x-0 md:opacity-100'
      "
    >
      <AgentSidebar
        :agents="agents"
        :messages="allMessages"
        :selected-id="selectedAgentId"
        :last-read-at="lastReadAt"
        :connected="wsConnected"
        :healthy="healthy"
        @select="selectAgent"
      />
    </div>

    <main
      class="flex h-full min-w-0 flex-1 flex-col bg-surface transition-panel duration-300 ease-out"
      :class="
        mobileView === 'chat'
          ? 'fixed inset-0 z-30 md:static'
          : 'hidden md:flex'
      "
    >
      <ChatHeader
        :title="selectedAgent.label"
        :subtitle="selectedAgent.description"
        :icon="selectedAgent.icon"
        :mood="currentMood"
        :global-mood="globalMood"
        :show-back="mobileView === 'chat'"
        @back="backToList"
      />

      <p v-if="error" class="bg-red-500/10 px-4 py-2 text-center text-xs text-red-300">{{ error }}</p>

      <EnvWorkspace
        v-if="selectedAgentId === 'env'"
        :messages="allMessages"
        :loading="loading"
        :agent="selectedAgent"
        :live="wsConnected"
        @send="onSend"
        @screenshot="requestScreenshot"
        @camera="requestCamera"
        @responded="onResponded"
      />

      <template v-else>
        <MessageList
          :messages="chatMessages"
          :loading="loading"
          :agent="selectedAgent"
          @responded="onResponded"
        />
        <ChatInput @send="onSend" />
      </template>
    </main>
  </div>
</template>
