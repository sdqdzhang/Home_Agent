<script setup>
import { ref } from 'vue'

defineProps({
  msg: { type: Object, required: true },
})

const open = ref(false)

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

const summary = (msg) => msg.message?.summary || msg.message?.text || '执行日志'
const lines = (msg) => {
  const log = msg.message?.log || msg.message?.lines || msg.message?.text || ''
  return Array.isArray(log) ? log.join('\n') : String(log)
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="overflow-hidden rounded-xl border border-surface-border bg-surface-raised">
      <button
        type="button"
        class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/5"
        @click="open = !open"
      >
        <div class="min-w-0 flex-1">
          <p class="truncate text-sm text-slate-200">{{ summary(msg) }}</p>
          <p class="text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
        </div>
        <span class="shrink-0 text-slate-400 transition-transform" :class="open && 'rotate-180'">▼</span>
      </button>

      <div v-show="open" class="border-t border-surface-border">
        <pre
          class="max-h-64 overflow-auto bg-black px-4 py-3 font-mono text-xs leading-relaxed text-emerald-400 scrollbar-thin"
        >{{ lines(msg) }}</pre>
      </div>
    </div>
  </div>
</template>
