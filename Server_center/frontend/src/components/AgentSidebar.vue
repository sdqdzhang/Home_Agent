<script setup>
import HealthBanner from './HealthBanner.vue'
import { USER_SENDER } from '../config/agents.js'
import { belongsToAgent, countsAsUnread, isAgentWorking, isUrgentUnread, messageSummary } from '../utils/messages.js'

const props = defineProps({
  agents: { type: Array, required: true },
  messages: { type: Array, required: true },
  selectedId: { type: String, required: true },
  lastReadAt: { type: Object, required: true },
  connected: { type: Boolean, default: false },
  healthy: { type: Boolean, default: true },
})

const emit = defineEmits(['select'])

function agentMessages(agent) {
  return props.messages.filter((m) => belongsToAgent(m, agent))
}

function lastMessage(agent) {
  const list = agentMessages(agent)
  if (!list.length) return null
  return list.reduce((a, b) => (a.timestamp >= b.timestamp ? a : b))
}

function unreadCount(agent) {
  const readAt = props.lastReadAt[agent.id] || 0
  return agentMessages(agent).filter(
    (m) => countsAsUnread(m) && m.timestamp > readAt && m.name !== USER_SENDER,
  ).length
}

function hasUrgent(agent) {
  const readAt = props.lastReadAt[agent.id] || 0
  return agentMessages(agent).some(
    (m) => isUrgentUnread(m, agent) && m.timestamp > readAt,
  )
}

function preview(agent) {
  const last = lastMessage(agent)
  if (!last) return '暂无消息'
  return messageSummary(last)
}

function working(agent) {
  return isAgentWorking(props.messages, agent)
}
</script>

<template>
  <aside class="flex h-full w-full flex-col border-surface-border bg-surface-raised md:w-sidebar md:shrink-0 md:border-r">
    <HealthBanner :connected="connected" :healthy="healthy" />

    <div class="mt-2 px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
      智能体
    </div>

    <nav class="flex-1 overflow-y-auto scrollbar-thin px-2 pb-3">
      <button
        v-for="agent in agents"
        :key="agent.id"
        type="button"
        class="mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors"
        :class="
          selectedId === agent.id
            ? 'bg-indigo-500/15 ring-1 ring-indigo-500/40'
            : 'hover:bg-white/5'
        "
        @click="emit('select', agent.id)"
      >
        <div
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-lg"
          :class="selectedId === agent.id ? 'bg-indigo-500/25' : 'bg-slate-700/80'"
        >
          {{ agent.icon || agent.label.slice(0, 1) }}
        </div>

        <div class="min-w-0 flex-1">
          <div class="flex items-center justify-between gap-2">
            <span class="truncate text-sm font-medium text-slate-100">{{ agent.label }}</span>
            <span class="shrink-0 text-base leading-none" :title="working(agent) ? '工作中' : '闲置'">
              {{ working(agent) ? '🔵' : '⚪' }}
            </span>
          </div>
          <p class="mt-0.5 truncate text-xs text-slate-400">{{ preview(agent) }}</p>
        </div>

        <div class="flex w-4 shrink-0 flex-col items-center gap-1">
          <span
            v-if="hasUrgent(agent)"
            class="h-2.5 w-2.5 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]"
            title="待审批"
          />
          <span
            v-else-if="unreadCount(agent) > 0"
            class="flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white"
          >
            {{ unreadCount(agent) > 9 ? '9+' : unreadCount(agent) }}
          </span>
        </div>
      </button>
    </nav>
  </aside>
</template>
