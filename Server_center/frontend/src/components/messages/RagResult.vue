<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function formatScore(score) {
  if (score == null || Number.isNaN(Number(score))) return ''
  return `${Math.round(Number(score) * 100)}%`
}

function sourceLabel(source, index) {
  const title = source.title || source.url || `来源 ${index + 1}`
  if (source.chunk_index != null && source.chunk_index >= 0) {
    return `${title} · 片段 ${source.chunk_index + 1}`
  }
  return title
}

function sourceMeta(source) {
  const parts = []
  if (source.doc_id) parts.push(`文档 ${source.doc_id}`)
  if (source.chunk_id) parts.push(`块 ${source.chunk_id}`)
  return parts.join(' · ')
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="rounded-xl border border-violet-500/30 bg-violet-500/5 px-4 py-3">
      <p class="text-xs font-medium uppercase tracking-wide text-violet-300">RAG 检索</p>
      <p v-if="msg.message?.query" class="mt-1 text-sm font-medium text-slate-200">
        Q: {{ msg.message.query }}
      </p>
      <p v-if="msg.message?.answer" class="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
        {{ msg.message.answer }}
      </p>

      <div v-if="msg.message?.sources?.length" class="mt-3 border-t border-violet-500/20 pt-2">
        <p class="mb-2 text-xs text-slate-500">
          引用来源 {{ msg.message.sources.length }} 条
          <span v-if="msg.message?.mode" class="text-violet-300/80"> · {{ msg.message.mode === 'summarized' ? '模型总结' : '直接返回' }}</span>
        </p>
        <div class="space-y-1.5">
          <details
            v-for="(source, index) in msg.message.sources"
            :key="source.chunk_id || `${source.doc_id}-${index}`"
            class="group overflow-hidden rounded-lg border border-violet-500/15 bg-black/20"
          >
            <summary
              class="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-slate-300 marker:content-none hover:bg-violet-500/10"
            >
              <span class="shrink-0 text-slate-500 transition-transform group-open:rotate-90">▶</span>
              <span class="min-w-0 flex-1 truncate">📄 {{ sourceLabel(source, index) }}</span>
              <span
                v-if="source.score != null"
                class="shrink-0 rounded bg-violet-500/20 px-1.5 py-0.5 text-[10px] text-violet-200"
              >
                {{ formatScore(source.score) }}
              </span>
            </summary>
            <div class="border-t border-violet-500/10 px-3 py-2">
              <p v-if="sourceMeta(source)" class="mb-2 font-mono text-[10px] text-slate-500">
                {{ sourceMeta(source) }}
              </p>
              <pre
                v-if="source.snippet"
                class="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-400 scrollbar-thin"
              >{{ source.snippet }}</pre>
              <p v-else class="text-[11px] text-slate-500">无片段内容</p>
            </div>
          </details>
        </div>
      </div>

      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>

<style scoped>
details > summary::-webkit-details-marker {
  display: none;
}
</style>
