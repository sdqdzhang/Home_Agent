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
    <div class="rounded-xl border border-zinc-700/80 bg-zinc-900/50 px-4 py-3">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <span class="text-lg text-zinc-100">{{ msg.message?.mood || '—' }}</span>
        <span
          v-if="msg.message?.persona_display_name || msg.message?.personality"
          class="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300"
        >
          {{ msg.message?.persona_display_name || msg.message?.personality }}
        </span>
      </div>
      <p v-if="msg.message?.text" class="text-sm text-zinc-300">{{ msg.message.text }}</p>
      <div v-if="msg.message?.traits?.length" class="mt-2 flex flex-wrap gap-1">
        <span
          v-for="(t, i) in msg.message.traits"
          :key="i"
          class="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400"
        >
          {{ t }}
        </span>
      </div>
      <p class="mt-2 text-xs text-zinc-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
