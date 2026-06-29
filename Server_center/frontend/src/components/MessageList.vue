<script setup>
import MessageItem from './MessageItem.vue'
import ModuleEmpty from './ModuleEmpty.vue'
import { useChatScroll } from '../utils/useChatScroll.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, default: null },
})

const emit = defineEmits(['responded'])

const { listEl, scrollToBottom } = useChatScroll(() => props.messages)

defineExpose({ scrollToBottom })

function onResponded(msg) {
  emit('responded', msg)
}
</script>

<template>
  <div ref="listEl" class="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin md:px-6">
    <div v-if="loading" class="flex h-full items-center justify-center text-sm text-slate-500">
      加载消息中…
    </div>
    <ModuleEmpty v-else-if="!messages.length && agent" :agent="agent" />
    <div v-else class="mx-auto flex max-w-3xl flex-col gap-4">
      <MessageItem
        v-for="msg in messages"
        :key="msg.id"
        :msg="msg"
        @responded="onResponded"
      />
    </div>
  </div>
</template>
