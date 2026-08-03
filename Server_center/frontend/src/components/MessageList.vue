<script setup>
import MessageItem from './MessageItem.vue'
import ModuleEmpty from './ModuleEmpty.vue'
import { useChatScroll } from '../utils/useChatScroll.js'
import { formatWeChatTimeLabel, shouldShowWeChatTimeDivider } from '../utils/messages.js'

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

function showTimeDivider(index) {
  const curr = props.messages[index]
  const prev = index > 0 ? props.messages[index - 1] : null
  return shouldShowWeChatTimeDivider(prev?.timestamp, curr?.timestamp)
}
</script>

<template>
  <div ref="listEl" class="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin md:px-6">
    <div v-if="loading" class="flex h-full items-center justify-center text-sm text-slate-500">
      加载消息中…
    </div>
    <ModuleEmpty v-else-if="!messages.length && agent" :agent="agent" />
    <div v-else class="mx-auto flex max-w-3xl flex-col gap-4">
      <template v-for="(msg, index) in messages" :key="msg.id">
        <div
          v-if="showTimeDivider(index)"
          class="flex justify-center py-1"
        >
          <span class="rounded-md bg-slate-800/60 px-2.5 py-0.5 text-[11px] text-slate-400">
            {{ formatWeChatTimeLabel(msg.timestamp) }}
          </span>
        </div>
        <MessageItem
          :msg="msg"
          @responded="onResponded"
        />
      </template>
    </div>
  </div>
</template>
