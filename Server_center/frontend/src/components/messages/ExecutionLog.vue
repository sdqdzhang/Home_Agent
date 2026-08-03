<script setup>
import { computed, ref, watch } from 'vue'
import {
  buildCrawlFileText,
  downloadTextFile,
  suggestCrawlFilename,
} from '../../utils/crawler.js'

const props = defineProps({
  msg: { type: Object, required: true },
})

const open = ref(false)
const saveHint = ref('')

const toolLabel = computed(() => {
  const tool = props.msg.message?.tool || props.msg.message?.payload?.tool || ''
  if (tool === 'crawler_fetch') return '网页爬取'
  if (tool === 'executor_run') return '执行'
  return ''
})

const summary = computed(
  () => props.msg.message?.summary || props.msg.message?.text || '执行日志',
)

const lines = computed(() => {
  const log = props.msg.message?.log || props.msg.message?.lines
  if (Array.isArray(log) && log.length) return log.join('\n')
  if (typeof log === 'string' && log.trim()) return log

  const result = props.msg.message?.payload?.result
  if (result && typeof result === 'object') {
    const parts = []
    if (result.stdout) parts.push(String(result.stdout).trim())
    if (result.stderr) parts.push(`[stderr]\n${String(result.stderr).trim()}`)
    if (result.reason) parts.push(`[reason] ${result.reason}`)
    if (result.error) parts.push(`[error] ${result.error}`)
    if (parts.length) return parts.join('\n\n')
  }
  return ''
})

const crawlResult = computed(() => {
  const result = props.msg.message?.payload?.result
  return result && typeof result === 'object' && (result.content || result.title || result.url)
    ? result
    : null
})
const crawlContent = computed(() => String(crawlResult.value?.content || '').trim())

watch(
  () => props.msg.message?.status,
  (status) => {
    if (status === 'running') open.value = true
  },
  { immediate: true },
)

function onSaveCrawlFile() {
  if (!crawlContent.value) return
  downloadTextFile(buildCrawlFileText(crawlResult.value), suggestCrawlFilename(crawlResult.value))
  saveHint.value = '已下载'
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
          <p v-if="toolLabel" class="mb-0.5 text-[11px] font-medium text-slate-500">{{ toolLabel }}</p>
          <p class="truncate text-sm text-slate-200">{{ summary }}</p>
          <p class="text-xs text-slate-500">
            <span v-if="msg.message?.status === 'running'" class="text-amber-400">执行中…</span>
            <span v-else-if="msg.message?.status === 'cancelled'" class="text-red-400">已终止</span>
            <span v-else-if="msg.message?.status === 'completed'" class="text-emerald-400">完成</span>
            <span v-else-if="msg.message?.status === 'failed'" class="text-red-400">失败</span>
          </p>
        </div>
        <span class="shrink-0 text-slate-400 transition-transform" :class="open && 'rotate-180'">▼</span>
      </button>

      <div v-show="open" class="border-t border-surface-border">
        <div v-if="crawlContent" class="border-b border-surface-border px-4 py-3">
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p class="text-[11px] text-slate-400">过滤后正文</p>
            <button
              type="button"
              class="rounded-md bg-sky-600/90 px-2.5 py-1 text-[11px] text-white hover:bg-sky-500"
              @click.stop="onSaveCrawlFile"
            >
              保存为文件
            </button>
          </div>
          <p v-if="saveHint" class="mb-2 text-[11px] text-emerald-400">{{ saveHint }}</p>
          <pre
            class="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-300 scrollbar-thin"
          >{{ crawlContent }}</pre>
        </div>
        <pre
          class="max-h-64 overflow-auto bg-black px-4 py-3 font-mono text-xs leading-relaxed text-emerald-400 scrollbar-thin"
        >{{ lines || '（暂无日志）' }}</pre>
      </div>
    </div>
  </div>
</template>
