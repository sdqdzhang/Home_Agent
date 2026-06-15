<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="rounded-xl border border-violet-500/30 bg-violet-500/5 px-4 py-3">
      <p class="text-xs font-medium uppercase tracking-wide text-violet-300">RAG 检索</p>
      <p v-if="msg.message?.query" class="mt-1 text-sm font-medium text-slate-200">
        Q: {{ msg.message.query }}
      </p>
      <p v-if="msg.message?.answer" class="mt-2 text-sm leading-relaxed text-slate-300">
        {{ msg.message.answer }}
      </p>
      <ul v-if="msg.message?.sources?.length" class="mt-3 space-y-1 border-t border-violet-500/20 pt-2">
        <li
          v-for="(s, i) in msg.message.sources"
          :key="i"
          class="truncate text-xs text-slate-400"
        >
          📄 {{ s.title || s.url || s }}
        </li>
      </ul>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
