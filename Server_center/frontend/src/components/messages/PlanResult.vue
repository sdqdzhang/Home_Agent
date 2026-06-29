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
    <div class="rounded-xl border border-sky-500/30 bg-sky-500/5 px-4 py-3">
      <p class="text-xs font-medium text-sky-300">任务规划</p>
      <p v-if="msg.message?.goal" class="mt-2 text-sm font-medium text-slate-200">
        目标：{{ msg.message.goal }}
      </p>
      <p v-if="msg.message?.summary" class="mt-2 text-sm text-slate-300">
        {{ msg.message.summary }}
      </p>
      <ol v-if="msg.message?.steps?.length" class="mt-3 space-y-1 border-t border-sky-500/20 pt-2">
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
      <p v-if="msg.message?.status" class="mt-2 text-xs text-slate-500">
        状态：{{ msg.message.status }}
      </p>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
