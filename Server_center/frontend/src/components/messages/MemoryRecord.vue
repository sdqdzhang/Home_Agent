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
    <div class="rounded-xl border border-amber-500/25 bg-amber-500/5 px-4 py-3">
      <p class="text-xs font-medium text-amber-200">🧠 记忆记录</p>
      <p v-if="msg.message?.key" class="mt-1 font-mono text-sm text-amber-100">{{ msg.message.key }}</p>
      <p v-if="msg.message?.summary || msg.message?.text" class="mt-2 text-sm text-slate-300">
        {{ msg.message.summary || msg.message.text }}
      </p>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
