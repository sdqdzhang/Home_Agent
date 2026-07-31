<script setup>
import { computed } from 'vue'
import TaskGraphCanvas from '../planning/TaskGraphCanvas.vue'

const props = defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

const body = computed(() => props.msg.message || {})
const graph = computed(() => body.value.graph || null)
const nodeStatus = computed(() => body.value.node_status || {})
const phase = computed(() => body.value.phase || body.value.status || '')

const phaseLabel = computed(() => {
  const p = phase.value
  if (p === 'collecting') return '收集信息'
  if (p === 'running' || p === 'planned') return '执行中'
  if (p === 'done' || p === 'succeeded') return '已完成'
  if (p === 'failed') return '失败'
  if (p === 'draft') return '草稿'
  return p || '规划'
})

const statusClass = computed(() => {
  const p = phase.value
  if (p === 'failed' || body.value.ok === false) return 'bg-red-500/20 text-red-300'
  if (p === 'done' || p === 'succeeded') return 'bg-emerald-500/20 text-emerald-300'
  if (p === 'running' || p === 'collecting') return 'bg-amber-500/20 text-amber-200'
  return 'bg-slate-500/20 text-slate-300'
})
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="rounded-xl border border-sky-500/30 bg-sky-500/5 px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium text-sky-300">任务规划</p>
        <span class="rounded px-1.5 py-0.5 text-[10px] tracking-wide" :class="statusClass">
          {{ phaseLabel }}
        </span>
      </div>

      <p v-if="body.ok === false && body.error" class="mt-2 text-sm text-red-300">
        {{ body.error }}
      </p>

      <p v-if="body.goal" class="mt-2 whitespace-pre-wrap text-sm font-medium text-slate-200">
        目标：{{ body.goal }}
      </p>
      <p v-if="body.summary" class="mt-2 text-sm text-slate-300">
        {{ body.summary }}
      </p>
      <p v-else-if="body.text && !graph?.nodes?.length" class="mt-2 text-sm text-slate-400">
        {{ body.text }}
      </p>

      <div
        v-if="graph?.nodes?.length"
        class="mt-3 overflow-hidden rounded-lg border border-sky-500/20 bg-slate-950/40"
      >
        <TaskGraphCanvas :graph="graph" :node-status="nodeStatus" compact />
      </div>

      <p
        v-if="body.files?.length"
        class="mt-2 text-xs text-slate-500"
      >
        产出文件 {{ body.files.length }} 个
      </p>

      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
