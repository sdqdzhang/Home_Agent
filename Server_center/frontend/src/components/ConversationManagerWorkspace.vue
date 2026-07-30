<script setup>
import { computed } from 'vue'
import { conversationManagerMessages, latestSnapshot } from '../utils/conversationManager.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

defineEmits(['error'])

const channelMessages = computed(() => conversationManagerMessages(props.messages, props.agent))
const snapshot = computed(() => latestSnapshot(props.messages, props.agent))

const metrics = computed(() => {
  const s = snapshot.value || {}
  return {
    session_id: s.session_id || '—',
    turn_index: s.turn_index ?? '—',
    context_used_tokens: s.context_used_tokens ?? '—',
    context_limit_tokens: s.context_limit_tokens ?? '—',
    context_remaining_ratio: s.context_remaining_ratio ?? null,
    turns_since_state_update: s.turns_since_state_update ?? '—',
    last_trigger_rules: Array.isArray(s.last_trigger_rules) ? s.last_trigger_rules : [],
    last_analyzer_mode: s.last_analyzer_mode || '—',
    last_event: s.last_event || '—',
    updated_at: s.updated_at || '—',
  }
})

const state = computed(() => snapshot.value?.conversation_state || null)
const summary = computed(() => snapshot.value?.conversation_summary || '')
const openTasks = computed(() =>
  Array.isArray(snapshot.value?.open_tasks) ? snapshot.value.open_tasks : [],
)
const memoryCandidates = computed(() =>
  Array.isArray(snapshot.value?.memory_candidates) ? snapshot.value.memory_candidates : [],
)
const importantFiles = computed(() =>
  Array.isArray(snapshot.value?.important_files) ? snapshot.value.important_files : [],
)
const recentTools = computed(() =>
  Array.isArray(snapshot.value?.recent_tool_calls) ? snapshot.value.recent_tool_calls : [],
)
const moduleLogTail = computed(() =>
  Array.isArray(snapshot.value?.module_log_tail) ? snapshot.value.module_log_tail : [],
)

const pressurePct = computed(() => {
  const r = metrics.value.context_remaining_ratio
  if (typeof r !== 'number' || Number.isNaN(r)) return null
  return Math.max(0, Math.min(100, Math.round((1 - r) * 100)))
})

function preview(text, limit = 120) {
  const one = String(text || '').replace(/\n/g, ' ').trim()
  if (!one) return '—'
  return one.length > limit ? `${one.slice(0, limit)}…` : one
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-auto px-4 py-4 text-sm text-zinc-200">
    <p class="mb-3 text-xs text-zinc-500">
      程序维护的会话指标与 Analyzer 产出（只读）。主对话模型不直接调用本模块。
    </p>

    <p v-if="loading && !snapshot" class="text-zinc-500">加载中…</p>
    <p v-else-if="!snapshot" class="text-zinc-500">尚无 cm_snapshot。主对话跑通后将由 Conversation Manager 推送。</p>

    <template v-else>
      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">运行指标</h2>
        <dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-xs md:grid-cols-3">
          <div>
            <dt class="text-zinc-500">session</dt>
            <dd class="font-mono text-zinc-200">{{ metrics.session_id }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">turn</dt>
            <dd class="font-mono">{{ metrics.turn_index }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">tokens</dt>
            <dd class="font-mono">{{ metrics.context_used_tokens }} / {{ metrics.context_limit_tokens }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">距上次 State 更新</dt>
            <dd class="font-mono">{{ metrics.turns_since_state_update }} 轮</dd>
          </div>
          <div>
            <dt class="text-zinc-500">上次 Analyzer</dt>
            <dd>{{ metrics.last_analyzer_mode }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">上次事件</dt>
            <dd>{{ metrics.last_event }}</dd>
          </div>
          <div class="col-span-2 md:col-span-3">
            <dt class="text-zinc-500">更新时间</dt>
            <dd class="font-mono text-zinc-300">{{ metrics.updated_at }}</dd>
          </div>
        </dl>
        <div v-if="pressurePct !== null" class="mt-3">
          <div class="mb-1 flex justify-between text-xs text-zinc-500">
            <span>上下文压力</span>
            <span>{{ pressurePct }}%</span>
          </div>
          <div class="h-1.5 overflow-hidden rounded bg-zinc-800">
            <div
              class="h-full rounded bg-amber-500/80 transition-all"
              :style="{ width: `${pressurePct}%` }"
            />
          </div>
        </div>
        <div v-if="metrics.last_trigger_rules.length" class="mt-3">
          <p class="mb-1 text-xs text-zinc-500">上次触发规则</p>
          <div class="flex flex-wrap gap-1">
            <span
              v-for="rule in metrics.last_trigger_rules"
              :key="rule"
              class="rounded bg-zinc-800 px-2 py-0.5 font-mono text-[11px] text-amber-200/90"
            >{{ rule }}</span>
          </div>
        </div>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Conversation State</h2>
        <pre
          v-if="state"
          class="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] text-zinc-300"
        >{{ JSON.stringify(state, null, 2) }}</pre>
        <p v-else class="text-xs text-zinc-500">空</p>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Conversation Summary</h2>
        <p class="text-xs leading-relaxed text-zinc-300">{{ summary || '—' }}</p>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          Open Tasks（仅保存，不自动规划）
        </h2>
        <ul v-if="openTasks.length" class="space-y-2">
          <li
            v-for="(task, i) in openTasks"
            :key="task.id || i"
            class="rounded bg-zinc-950/60 px-2 py-1.5 text-xs"
          >
            <span class="font-medium text-zinc-200">{{ task.title || task.id || `task-${i}` }}</span>
            <p v-if="task.detail" class="mt-0.5 text-zinc-500">{{ preview(task.detail) }}</p>
          </li>
        </ul>
        <p v-else class="text-xs text-zinc-500">无</p>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Memory Candidates</h2>
        <ul v-if="memoryCandidates.length" class="space-y-2">
          <li
            v-for="(c, i) in memoryCandidates"
            :key="c.id || i"
            class="rounded bg-zinc-950/60 px-2 py-1.5 text-xs text-zinc-300"
          >
            {{ preview(c.content || c.text || JSON.stringify(c)) }}
          </li>
        </ul>
        <p v-else class="text-xs text-zinc-500">无</p>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">Important Files</h2>
        <ul v-if="importantFiles.length" class="space-y-1 font-mono text-[11px] text-zinc-400">
          <li v-for="(f, i) in importantFiles" :key="i">{{ typeof f === 'string' ? f : f.path || JSON.stringify(f) }}</li>
        </ul>
        <p v-else class="text-xs text-zinc-500">无</p>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">最近工具调用</h2>
        <ul v-if="recentTools.length" class="space-y-1 font-mono text-[11px] text-zinc-400">
          <li v-for="(t, i) in recentTools" :key="i">{{ preview(typeof t === 'string' ? t : JSON.stringify(t), 160) }}</li>
        </ul>
        <p v-else class="text-xs text-zinc-500">无</p>
      </section>

      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          模块日志尾（仅 UI / 调试，不进主模型上下文）
        </h2>
        <ul v-if="moduleLogTail.length" class="max-h-40 space-y-1 overflow-auto font-mono text-[11px] text-zinc-500">
          <li v-for="(row, i) in moduleLogTail" :key="i">{{ preview(typeof row === 'string' ? row : JSON.stringify(row), 200) }}</li>
        </ul>
        <p v-else class="text-xs text-zinc-500">无</p>
      </section>
    </template>

    <section v-if="channelMessages.length" class="mt-2 border-t border-zinc-800 pt-3">
      <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">频道消息 {{ channelMessages.length }}</h2>
      <ul class="max-h-32 space-y-1 overflow-auto text-[11px] text-zinc-600">
        <li v-for="m in channelMessages.slice(-20)" :key="m.id">
          <span class="font-mono">{{ m.msg_type }}</span>
          · {{ m.id }}
        </li>
      </ul>
    </section>
  </div>
</template>
