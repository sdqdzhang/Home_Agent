<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import MessageItem from './MessageItem.vue'
import ModuleEmpty from './ModuleEmpty.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, default: null },
})

const emit = defineEmits(['responded'])

const listEl = ref(null)

async function scrollToBottom(smooth = true) {
  await nextTick()
  if (!listEl.value) return
  listEl.value.scrollTo({
    top: listEl.value.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  })
}

watch(() => props.messages.length, () => scrollToBottom())
watch(() => props.messages[props.messages.length - 1]?.id, () => scrollToBottom())

onMounted(() => scrollToBottom(false))

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
