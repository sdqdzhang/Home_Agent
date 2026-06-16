<script setup>
import { computed } from 'vue'
import ChatInput from './ChatInput.vue'
import EnvDashboard from './EnvDashboard.vue'
import MessageItem from './MessageItem.vue'
import { envChatMessages, sortMessagesAsc } from '../utils/messages.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
  live: { type: Boolean, default: false },
})

const emit = defineEmits(['send', 'screenshot', 'camera', 'responded'])

const chatOnly = computed(() => sortMessagesAsc(envChatMessages(props.messages, props.agent)))
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <EnvDashboard :messages="messages" :agent="agent" :live="live" />

    <div class="flex items-center justify-between border-b border-surface-border bg-surface px-4 py-2 md:px-6">
      <span class="text-xs font-medium text-slate-400">对话与图像</span>
      <div class="flex gap-2">
        <button
          type="button"
          class="rounded-lg bg-indigo-500/20 px-3 py-1.5 text-xs text-indigo-200 ring-1 ring-indigo-500/40 hover:bg-indigo-500/30"
          @click="emit('screenshot')"
        >
          远程截图
        </button>
        <button
          type="button"
          class="rounded-lg bg-indigo-500/20 px-3 py-1.5 text-xs text-indigo-200 ring-1 ring-indigo-500/40 hover:bg-indigo-500/30"
          @click="emit('camera')"
        >
          摄像头拍照
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-3 py-3 scrollbar-thin md:px-6">
      <div v-if="loading" class="flex h-32 items-center justify-center text-sm text-slate-500">
        加载中…
      </div>
      <p v-else-if="!chatOnly.length" class="py-8 text-center text-sm text-slate-500">
        向环境感知模块提问，或点击「远程截图」/「摄像头拍照」
      </p>
      <div v-else class="mx-auto flex max-w-3xl flex-col gap-3">
        <MessageItem
          v-for="msg in chatOnly"
          :key="msg.id"
          :msg="msg"
          @responded="emit('responded', $event)"
        />
      </div>
    </div>

    <ChatInput @send="(text, att) => emit('send', text, att)" />
  </div>
</template>
