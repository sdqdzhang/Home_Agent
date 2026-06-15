<script setup>
import { ref } from 'vue'

const props = defineProps({
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['send'])

const text = ref('')
const files = ref([])
const dragging = ref(false)

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function addFiles(fileList) {
  for (const f of fileList) {
    files.value.push({ name: f.name, size: formatSize(f.size), raw: f })
  }
}

function onDrop(e) {
  dragging.value = false
  if (props.disabled) return
  addFiles(e.dataTransfer?.files || [])
}

function onFileInput(e) {
  addFiles(e.target.files || [])
  e.target.value = ''
}

function removeFile(i) {
  files.value.splice(i, 1)
}

function submit() {
  const value = text.value.trim()
  if (!value && !files.value.length) return
  emit(
    'send',
    value,
    files.value.map(({ name, size }) => ({ name, size })),
  )
  text.value = ''
  files.value = []
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div
    class="border-t border-surface-border bg-surface-raised px-3 py-3 md:px-6"
    @dragover.prevent="dragging = true"
    @dragleave.prevent="dragging = false"
    @drop.prevent="onDrop"
  >
    <div
      v-if="files.length"
      class="mb-2 flex flex-wrap gap-2"
    >
      <span
        v-for="(f, i) in files"
        :key="i"
        class="inline-flex items-center gap-1 rounded-full bg-slate-700 px-3 py-1 text-xs text-slate-200"
      >
        📎 {{ f.name }}
        <button type="button" class="text-slate-400 hover:text-white" @click="removeFile(i)">×</button>
      </span>
    </div>

    <div
      class="flex items-end gap-2 rounded-2xl border bg-surface px-3 py-2 transition-colors"
      :class="dragging ? 'border-indigo-500 bg-indigo-500/5' : 'border-surface-border'"
    >
      <label class="shrink-0 cursor-pointer rounded-lg p-2 text-slate-400 hover:bg-white/5 hover:text-slate-200">
        <input type="file" multiple class="hidden" :disabled="disabled" @change="onFileInput" />
        <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
        </svg>
      </label>

      <textarea
        v-model="text"
        rows="1"
        :disabled="disabled"
        placeholder="输入消息，或拖拽文件到此处…"
        class="max-h-32 min-h-[2.5rem] flex-1 resize-none bg-transparent py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
        @keydown="onKeydown"
      />

      <button
        type="button"
        class="shrink-0 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:opacity-40"
        :disabled="disabled || (!text.trim() && !files.length)"
        @click="submit"
      >
        发送
      </button>
    </div>
  </div>
</template>
