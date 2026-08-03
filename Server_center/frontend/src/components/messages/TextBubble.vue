<script setup>
import { computed } from 'vue'
import { isUserMessage } from '../../utils/messages.js'

const props = defineProps({
  msg: { type: Object, required: true },
})

const isUser = computed(() => isUserMessage(props.msg))
</script>

<template>
  <div class="flex w-full" :class="isUser ? 'justify-end' : 'justify-start'">
    <div
      class="max-w-[min(85%,32rem)] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm"
      :class="
        isUser
          ? 'rounded-br-md bg-agent-user text-white'
          : 'rounded-bl-md bg-agent-bubble text-slate-100'
      "
    >
      <p class="whitespace-pre-wrap">{{ msg.message?.text || '(空消息)' }}</p>
      <div
        v-if="msg.message?.attachments?.length"
        class="mt-2 space-y-1 border-t border-white/10 pt-2 text-xs opacity-90"
      >
        <div v-for="(f, i) in msg.message.attachments" :key="i">📎 {{ f.name }} ({{ f.size }})</div>
      </div>
    </div>
  </div>
</template>
