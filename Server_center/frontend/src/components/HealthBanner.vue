<script setup>
defineProps({
  connected: { type: Boolean, default: false },
  healthy: { type: Boolean, default: true },
})
</script>

<template>
  <div
    class="mx-3 mt-3 rounded-lg border px-3 py-2.5 text-sm"
    :class="
      healthy && connected
        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
        : 'border-amber-500/30 bg-amber-500/10 text-amber-200'
    "
  >
    <div class="flex items-center gap-2 font-medium">
      <span
        class="inline-block h-2 w-2 rounded-full"
        :class="healthy && connected ? 'bg-emerald-400' : 'bg-amber-400'"
      />
      <span v-if="healthy && connected">系统运行正常</span>
      <span v-else-if="!connected">连接中断，正在重连…</span>
      <span v-else>服务异常</span>
    </div>
    <p class="mt-1 text-xs opacity-80">Server Center · 消息中转站</p>
  </div>
</template>
