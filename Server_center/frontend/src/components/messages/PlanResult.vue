<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function nodeLine(node) {
  if (!node) return ''
  if (node.kind === 'process') {
    return `${node.id} [process/${node.output?.type || '?'}] ${node.requirement || ''}`
  }
  return `${node.id} [action/${node.output?.type || '?'}] ${node.instruction || ''}`
}

function inputLabel(inp) {
  const from = inp.from || inp.from_node || '?'
  return `${from}:${inp.role || '?'}`
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="rounded-xl border border-sky-500/30 bg-sky-500/5 px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium text-sky-300">任务规划</p>
        <span
          v-if="msg.message?.status"
          class="rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide"
          :class="
            msg.message.status === 'failed'
              ? 'bg-red-500/20 text-red-300'
              : msg.message.status === 'draft'
                ? 'bg-sky-500/20 text-sky-200'
                : 'bg-slate-500/20 text-slate-300'
          "
        >
          {{ msg.message.status }}
        </span>
      </div>

      <p v-if="msg.message?.ok === false && msg.message?.error" class="mt-2 text-sm text-red-300">
        {{ msg.message.error }}
      </p>

      <p v-if="msg.message?.goal" class="mt-2 whitespace-pre-wrap text-sm font-medium text-slate-200">
        目标：{{ msg.message.goal }}
      </p>
      <p v-if="msg.message?.summary" class="mt-2 text-sm text-slate-300">
        {{ msg.message.summary }}
      </p>

      <!-- TaskGraph -->
      <ol
        v-if="msg.message?.graph?.nodes?.length"
        class="mt-3 space-y-2 border-t border-sky-500/20 pt-2"
      >
        <li
          v-for="node in msg.message.graph.nodes"
          :key="node.id"
          class="text-sm text-slate-300"
        >
          <p class="font-medium text-slate-200">{{ nodeLine(node) }}</p>
          <p v-if="node.inputs?.length" class="mt-0.5 text-xs text-slate-500">
            ←
            {{ node.inputs.map(inputLabel).join(' · ') }}
          </p>
        </li>
      </ol>

      <!-- 旧 steps 兼容 -->
      <ol
        v-else-if="msg.message?.steps?.length"
        class="mt-3 space-y-1 border-t border-sky-500/20 pt-2"
      >
        <li
          v-for="(step, i) in msg.message.steps"
          :key="i"
          class="text-sm text-slate-300"
        >
          <span class="text-slate-500">{{ i + 1 }}.</span>
          {{ step.title || step.action || step }}
          <span v-if="step.target_module" class="ml-1 text-xs text-sky-300/80">
            → {{ step.target_module }}
          </span>
        </li>
      </ol>

      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
