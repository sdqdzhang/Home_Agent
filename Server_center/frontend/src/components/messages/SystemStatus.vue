<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}
</script>

<template>
  <div class="w-full text-center">
    <p class="inline-block max-w-xl text-xs leading-relaxed text-slate-500">
      <span class="text-slate-600">[{{ formatTime(msg.timestamp) }}]</span>
      {{ msg.message?.text || msg.message?.summary || '系统状态更新' }}
    </p>
  </div>
</template>
