<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function preview(text, limit = 200) {
  const s = String(text || '')
  return s.length > limit ? `${s.slice(0, limit)}…` : s
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div
      class="rounded-xl border px-4 py-3"
      :class="
        msg.message?.ok === false
          ? 'border-red-500/30 bg-red-500/5'
          : 'border-teal-500/30 bg-teal-500/5'
      "
    >
      <p
        class="text-xs font-medium"
        :class="msg.message?.ok === false ? 'text-red-300' : 'text-teal-300'"
      >
        处理结果
        <span v-if="msg.message?.ok === false" class="ml-2 text-red-400">失败</span>
        <span v-else-if="msg.message?.output?.id" class="ml-2 text-slate-500">
          {{ msg.message.output.id }}
        </span>
      </p>

      <p v-if="msg.message?.requirement" class="mt-2 text-sm text-slate-300">
        <span class="text-slate-500">要求：</span>{{ msg.message.requirement }}
      </p>

      <p v-if="msg.message?.error" class="mt-2 text-sm text-red-300">
        {{ msg.message.error }}
      </p>

      <template v-if="msg.message?.output">
        <p class="mt-2 text-xs text-slate-500">
          type={{ msg.message.output.type }}
          · producer={{ msg.message.output.producer }}
        </p>
        <pre
          class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-black/25 px-3 py-2 font-mono text-xs text-slate-200"
        >{{ preview(msg.message.output.content, 4000) }}</pre>
      </template>

      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
