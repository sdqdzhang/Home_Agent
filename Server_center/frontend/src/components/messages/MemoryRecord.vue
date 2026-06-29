<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function kindLabel(kind) {
  if (kind === 'insight') return '洞察'
  if (kind === 'observation') return '观察'
  return kind || '记忆'
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3">
      <div class="flex flex-wrap items-center gap-2">
        <p class="text-xs font-medium text-amber-200">🧠 记忆记录</p>
        <span
          v-if="msg.message?.kind"
          class="rounded bg-amber-500/15 px-1.5 py-0.5 text-xs text-amber-100/90"
        >
          {{ kindLabel(msg.message.kind) }}
        </span>
        <span
          v-if="msg.message?.importance != null"
          class="rounded bg-slate-700/60 px-1.5 py-0.5 text-xs text-slate-300"
        >
          重要性 {{ msg.message.importance }}
        </span>
      </div>
      <p v-if="msg.message?.tag" class="mt-1 text-xs text-amber-300/90">标签：[{{ msg.message.tag }}]</p>
      <p v-if="msg.message?.key" class="mt-1 font-mono text-sm text-amber-100">{{ msg.message.key }}</p>
      <p v-if="msg.message?.summary || msg.message?.text" class="mt-2 text-sm text-slate-300">
        {{ msg.message.summary || msg.message.text }}
      </p>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
