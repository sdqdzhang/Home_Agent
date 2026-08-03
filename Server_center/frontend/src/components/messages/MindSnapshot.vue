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
    <div class="rounded-lg border border-zinc-700/70 bg-zinc-900/40 px-3 py-2 text-xs text-zinc-400">
      <span class="text-zinc-300">心智快照</span>
      <span v-if="msg.message?.persona?.display_name || msg.message?.persona_display_name">
        · {{ msg.message?.persona?.display_name || msg.message?.persona_display_name }}
      </span>
      <span v-if="msg.message?.enabled === false" class="ml-1 text-zinc-500">（模块关闭）</span>
      <span v-else-if="msg.message?.enabled === true" class="ml-1 text-teal-500/80">（已开启）</span>
      <p class="mt-1 text-[10px] text-zinc-600">{{ formatTime(msg.timestamp) }} · 详情见本页工作台，不作为聊天记录</p>
    </div>
  </div>
</template>
