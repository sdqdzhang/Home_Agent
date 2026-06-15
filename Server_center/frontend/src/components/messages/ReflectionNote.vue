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
    <div class="rounded-xl border border-cyan-500/30 bg-cyan-500/5 px-4 py-3">
      <p class="text-xs font-medium text-cyan-300">自省与纠错</p>
      <p v-if="msg.message?.issue" class="mt-2 text-sm text-slate-200">
        <span class="text-slate-500">问题：</span>{{ msg.message.issue }}
      </p>
      <p v-if="msg.message?.analysis" class="mt-2 text-sm text-slate-300">
        <span class="text-slate-500">分析：</span>{{ msg.message.analysis }}
      </p>
      <p v-if="msg.message?.correction" class="mt-2 text-sm text-emerald-300">
        <span class="text-slate-500">纠正：</span>{{ msg.message.correction }}
      </p>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
