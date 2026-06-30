<script setup>
import { computed, ref, watch } from 'vue'
import {
  SECURITY_LIST_TABS,
  requestSecurityLists,
  securityListsErrorText,
} from '../utils/securityLists.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  open: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'error'])

const busy = ref(false)
const statusText = ref('')
const errorText = ref('')
const activeTab = ref('white_commands')
const lists = ref({
  white_commands: [],
  black_commands: [],
  white_directories: [],
  black_directories: [],
})

const newItem = ref('')
const editingIndex = ref(-1)
const editingValue = ref('')

const currentItems = computed({
  get: () => lists.value[activeTab.value] || [],
  set: (items) => {
    lists.value = { ...lists.value, [activeTab.value]: items }
  },
})

const activeLabel = computed(
  () => SECURITY_LIST_TABS.find((t) => t.key === activeTab.value)?.label || activeTab.value,
)

function getMessages() {
  return props.messages
}

function resetEditor() {
  newItem.value = ''
  editingIndex.value = -1
  editingValue.value = ''
}

watch(
  () => props.open,
  (visible) => {
    if (visible) {
      loadLists()
    } else {
      resetEditor()
      errorText.value = ''
    }
  },
)

watch(activeTab, () => {
  resetEditor()
})

async function loadLists() {
  busy.value = true
  errorText.value = ''
  try {
    const data = await requestSecurityLists(getMessages, { action: 'security_lists_get' })
    lists.value = {
      white_commands: [...(data.lists?.white_commands || [])],
      black_commands: [...(data.lists?.black_commands || [])],
      white_directories: [...(data.lists?.white_directories || [])],
      black_directories: [...(data.lists?.black_directories || [])],
    }
    statusText.value = `已加载 · ${new Date().toLocaleTimeString('zh-CN')}`
  } catch (e) {
    errorText.value = securityListsErrorText(e.code, e.message)
    emit('error', errorText.value)
  } finally {
    busy.value = false
  }
}

function addItem() {
  const text = newItem.value.trim()
  if (!text) return
  if (currentItems.value.some((item) => item.toLowerCase() === text.toLowerCase())) {
    errorText.value = '该条目已存在'
    return
  }
  currentItems.value = [...currentItems.value, text]
  newItem.value = ''
  errorText.value = ''
}

function startEdit(index) {
  editingIndex.value = index
  editingValue.value = currentItems.value[index]
}

function cancelEdit() {
  editingIndex.value = -1
  editingValue.value = ''
}

function applyEdit() {
  const text = editingValue.value.trim()
  if (!text) {
    errorText.value = '条目不能为空'
    return
  }
  const next = [...currentItems.value]
  const duplicate = next.some(
    (item, idx) => idx !== editingIndex.value && item.toLowerCase() === text.toLowerCase(),
  )
  if (duplicate) {
    errorText.value = '该条目已存在'
    return
  }
  next[editingIndex.value] = text
  currentItems.value = next
  cancelEdit()
  errorText.value = ''
}

function removeItem(index) {
  currentItems.value = currentItems.value.filter((_, idx) => idx !== index)
  if (editingIndex.value === index) cancelEdit()
}

async function saveCurrentList() {
  busy.value = true
  errorText.value = ''
  try {
    const data = await requestSecurityLists(getMessages, {
      action: 'security_lists_set',
      list_key: activeTab.value,
      items: currentItems.value,
    })
    lists.value = {
      white_commands: [...(data.lists?.white_commands || [])],
      black_commands: [...(data.lists?.black_commands || [])],
      white_directories: [...(data.lists?.white_directories || [])],
      black_directories: [...(data.lists?.black_directories || [])],
    }
    statusText.value = `已保存 ${activeLabel.value} · ${new Date().toLocaleTimeString('zh-CN')}`
    cancelEdit()
  } catch (e) {
    errorText.value = securityListsErrorText(e.code, e.message)
    emit('error', errorText.value)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
    @click.self="emit('close')"
  >
    <div
      class="flex max-h-[min(90vh,720px)] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-surface-border bg-surface-raised shadow-2xl"
      role="dialog"
      aria-labelledby="security-lists-title"
    >
      <header class="flex shrink-0 items-center justify-between gap-3 border-b border-surface-border px-4 py-3">
        <div>
          <h2 id="security-lists-title" class="text-base font-semibold text-slate-100">规则配置</h2>
          <p class="mt-0.5 text-xs text-slate-500">黑白命令与目录 · 保存后立即生效</p>
        </div>
        <button
          type="button"
          class="rounded-lg px-3 py-1.5 text-sm text-slate-400 hover:bg-white/5 hover:text-slate-200"
          @click="emit('close')"
        >
          关闭
        </button>
      </header>

      <div class="flex shrink-0 gap-1 overflow-x-auto border-b border-surface-border px-3 py-2">
        <button
          v-for="tab in SECURITY_LIST_TABS"
          :key="tab.key"
          type="button"
          class="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium transition"
          :class="
            activeTab === tab.key
              ? 'bg-indigo-500/20 text-indigo-200'
              : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
          "
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span class="ml-1 text-slate-500">({{ (lists[tab.key] || []).length }})</span>
        </button>
      </div>

      <p v-if="errorText" class="shrink-0 bg-red-500/10 px-4 py-2 text-xs text-red-300">{{ errorText }}</p>
      <p v-else-if="statusText" class="shrink-0 px-4 py-2 text-xs text-slate-500">{{ statusText }}</p>

      <ul class="min-h-0 flex-1 overflow-y-auto px-3 py-2 text-sm">
        <li v-if="!currentItems.length" class="px-2 py-6 text-center text-slate-500">暂无条目</li>
        <li
          v-for="(item, index) in currentItems"
          :key="`${activeTab}-${index}-${item}`"
          class="mb-1 flex items-center gap-2 rounded-lg bg-slate-800/50 px-2 py-1.5"
        >
          <template v-if="editingIndex === index">
            <input
              v-model="editingValue"
              type="text"
              class="min-w-0 flex-1 rounded border border-surface-border bg-surface px-2 py-1 font-mono text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
              @keyup.enter="applyEdit"
              @keyup.escape="cancelEdit"
            />
            <button
              type="button"
              class="shrink-0 rounded px-2 py-1 text-xs text-emerald-300 hover:bg-emerald-500/10"
              @click="applyEdit"
            >
              确定
            </button>
            <button
              type="button"
              class="shrink-0 rounded px-2 py-1 text-xs text-slate-400 hover:bg-white/5"
              @click="cancelEdit"
            >
              取消
            </button>
          </template>
          <template v-else>
            <span class="min-w-0 flex-1 truncate font-mono text-xs text-slate-200">{{ item }}</span>
            <button
              type="button"
              class="shrink-0 rounded px-2 py-1 text-xs text-slate-400 hover:bg-white/5 hover:text-indigo-200"
              :disabled="busy"
              @click="startEdit(index)"
            >
              编辑
            </button>
            <button
              type="button"
              class="shrink-0 rounded px-2 py-1 text-xs text-red-400 hover:bg-red-500/10"
              :disabled="busy"
              @click="removeItem(index)"
            >
              删除
            </button>
          </template>
        </li>
      </ul>

      <footer class="shrink-0 space-y-2 border-t border-surface-border px-4 py-3">
        <div class="flex gap-2">
          <input
            v-model="newItem"
            type="text"
            :placeholder="activeTab.includes('command') ? '命令首词，如 Get-ChildItem' : '目录路径前缀'"
            class="min-w-0 flex-1 rounded-lg border border-surface-border bg-surface px-3 py-2 font-mono text-xs text-slate-200 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
            :disabled="busy"
            @keyup.enter="addItem"
          />
          <button
            type="button"
            class="shrink-0 rounded-lg border border-surface-border px-3 py-2 text-xs text-slate-300 hover:bg-white/5 disabled:opacity-50"
            :disabled="busy"
            @click="addItem"
          >
            添加
          </button>
        </div>
        <div class="flex items-center justify-between gap-2">
          <button
            type="button"
            class="rounded-lg px-3 py-2 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200 disabled:opacity-50"
            :disabled="busy"
            @click="loadLists"
          >
            重新加载
          </button>
          <button
            type="button"
            class="rounded-lg bg-indigo-600 px-4 py-2 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            :disabled="busy"
            @click="saveCurrentList"
          >
            {{ busy ? '保存中…' : `保存「${activeLabel}」` }}
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>
