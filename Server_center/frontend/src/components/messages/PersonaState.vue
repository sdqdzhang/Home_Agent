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
    <div class="rounded-xl border border-pink-500/30 bg-pink-500/5 px-4 py-3">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <span class="text-lg">{{ msg.message?.mood || '—' }}</span>
        <span
          v-if="msg.message?.personality"
          class="rounded-full bg-pink-500/20 px-2 py-0.5 text-xs text-pink-200"
        >
          {{ msg.message.personality }}
        </span>
      </div>
      <p v-if="msg.message?.text" class="text-sm text-slate-300">{{ msg.message.text }}</p>
      <div v-if="msg.message?.traits?.length" class="mt-2 flex flex-wrap gap-1">
        <span
          v-for="(t, i) in msg.message.traits"
          :key="i"
          class="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-400"
        >
          {{ t }}
        </span>
      </div>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
