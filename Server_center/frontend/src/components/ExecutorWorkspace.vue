<script setup>
import { computed, ref } from 'vue'

import { sendMessageLocal } from '../api/client.js'
import {
  EXECUTOR_MODE_AUTO,
  EXECUTOR_MODES,
  executorModeLabel,
} from '../config/executorModes.js'
import ChatInput from './ChatInput.vue'
import MessageItem from './MessageItem.vue'
import {
  buildExecutorCancelMessage,
  executorWorkspaceMessages,
  findRunningExecutorJob,
  sortMessagesAsc,
} from '../utils/messages.js'
import { useChatScroll } from '../utils/useChatScroll.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

const emit = defineEmits(['send', 'responded', 'error'])

const TEXT_SUFFIXES = [
  '.txt', '.md', '.markdown', '.json', '.csv', '.log', '.xml', '.html', '.htm',
  '.yaml', '.yml', '.toml', '.ini', '.cfg', '.env', '.sql',
  '.py', '.js', '.ts', '.tsx', '.jsx', '.mjs', '.cjs', '.vue', '.svelte',
  '.java', '.kt', '.go', '.rs', '.c', '.h', '.cpp', '.hpp', '.cs', '.rb', '.php',
  '.sh', '.bash', '.bat', '.cmd', '.ps1', '.css', '.scss', '.less',
]

/** @type {import('vue').Ref<string>} */
const forceMode = ref(EXECUTOR_MODE_AUTO)
const sidebarOpen = ref(true)
const fileContent = ref('')
const loadError = ref('')
const fileInput = ref(null)
const cancelBusy = ref(false)

const hasBody = computed(() => fileContent.value.length > 0)
const runningJob = computed(() => findRunningExecutorJob(props.messages, props.agent))
const isForced = computed(() => forceMode.value !== EXECUTOR_MODE_AUTO)

const workspaceMessages = computed(() =>
  sortMessagesAsc(executorWorkspaceMessages(props.messages, props.agent)),
)

const { listEl, scrollToBottom } = useChatScroll(workspaceMessages)

const headerHint = computed(() => {
  if (isForced.value) {
    const m = EXECUTOR_MODES.find((x) => x.id === forceMode.value)
    return `已强制 ${m?.label || forceMode.value}：${m?.hint || ''}（调试用）`
  }
  return '自然语言交给执行模块自动选择子能力；侧栏正文仅作附件（有附件时必须是写入文件）'
})

function onChatSend(text, attachments) {
  const body = fileContent.value
  const trimmed = text.trim()
  if (!trimmed && !body && !attachments?.length) return

  if (body.length > 2_000_000) {
    loadError.value = '正文过大（>2MB），请拆分后发送'
    return
  }

  if (body && trimmed && !/写|保存|创建|新建|存入|覆盖|写入/.test(trimmed)) {
    loadError.value = '侧栏有正文时，请在消息中说明写入目标，如「将侧栏内容写入 workspace/123.py」'
    return
  }

  if (isForced.value && forceMode.value !== 'write_file' && (body || attachments?.length)) {
    loadError.value = `强制 ${executorModeLabel(forceMode.value)} 时不能附带正文；请选「自动路由」或「写入文件」`
    return
  }

  loadError.value = ''
  scrollToBottom(false)
  emit('send', trimmed, attachments, {
    mode: isForced.value ? forceMode.value : null,
    fileContent: body || null,
  })
}

function clearAttachedBody() {
  fileContent.value = ''
  loadError.value = ''
}

defineExpose({ clearAttachedBody })

async function cancelExecution() {
  if (!runningJob.value || cancelBusy.value) return
  cancelBusy.value = true
  loadError.value = ''
  try {
    const msg = buildExecutorCancelMessage(props.agent.id, runningJob.value.jobId)
    const result = await sendMessageLocal(msg)
    emit('responded', result.message)
  } catch (e) {
    loadError.value = e.message
    emit('error', e.message)
  } finally {
    cancelBusy.value = false
  }
}

function toggleSidebar() {
  sidebarOpen.value = !sidebarOpen.value
}

function onPickFile() {
  fileInput.value?.click()
}

async function onFileSelected(event) {
  const file = event.target.files?.[0]
  if (!file) return

  const lower = file.name.toLowerCase()
  const knownText = TEXT_SUFFIXES.some((s) => lower.endsWith(s))

  if (!knownText && file.size > 2 * 1024 * 1024) {
    loadError.value = '文件较大且非常见文本类型，请确认后重试或粘贴内容'
    event.target.value = ''
    return
  }

  try {
    const text = await file.text()
    if (text.includes('\u0000')) {
      loadError.value = '检测到二进制内容，请使用文本文件'
      return
    }
    fileContent.value = text
    loadError.value = ''
  } catch (e) {
    loadError.value = e.message || '读取文件失败'
    emit('error', loadError.value)
  } finally {
    event.target.value = ''
  }
}

function clearBody() {
  fileContent.value = ''
  loadError.value = ''
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <section class="flex min-h-0 min-w-0 flex-1 flex-col">
        <div
          class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-surface-border bg-indigo-500/5 px-4 py-2 md:px-5"
        >
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <p class="text-xs font-medium text-indigo-200">执行</p>
              <label class="flex items-center gap-1.5 text-[11px] text-slate-400">
                <span>mode</span>
                <select
                  v-model="forceMode"
                  class="rounded-md border border-surface-border bg-surface px-2 py-1 text-xs text-slate-200 outline-none focus:ring-1 focus:ring-indigo-500/40"
                >
                  <option :value="EXECUTOR_MODE_AUTO">自动路由</option>
                  <option v-for="m in EXECUTOR_MODES" :key="m.id" :value="m.id">
                    强制 · {{ m.label }}
                  </option>
                </select>
              </label>
            </div>
            <p class="mt-0.5 text-[11px] text-slate-500">{{ headerHint }}</p>
          </div>
          <button
            v-if="runningJob"
            type="button"
            class="shrink-0 rounded-lg bg-red-600/90 px-3 py-1.5 text-xs font-medium text-white hover:bg-red-500 disabled:opacity-50"
            :disabled="cancelBusy"
            @click="cancelExecution"
          >
            {{ cancelBusy ? '终止中…' : '终止执行' }}
          </button>
        </div>

        <div ref="listEl" class="flex-1 overflow-y-auto px-3 py-3 scrollbar-thin md:px-5">
          <div v-if="loading" class="flex h-32 items-center justify-center text-sm text-slate-500">加载中…</div>
          <p v-else-if="!workspaceMessages.length" class="py-10 text-center text-sm text-slate-500">
            例如「列出当前目录下的 .py 文件」「读取 README.md」或「用 Python 实现 parse_csv…」
          </p>
          <div v-else class="mx-auto flex max-w-2xl flex-col gap-3">
            <MessageItem
              v-for="msg in workspaceMessages"
              :key="msg.id"
              :msg="msg"
              @responded="emit('responded', $event)"
            />
          </div>
        </div>

        <p
          v-if="loadError"
          class="mx-4 mb-1 shrink-0 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300 md:mx-5"
        >
          {{ loadError }}
        </p>

        <ChatInput @send="onChatSend" />
      </section>

      <aside
        class="flex shrink-0 flex-col border-l border-surface-border bg-surface-raised/80 transition-[width] duration-200 ease-out"
        :class="sidebarOpen ? 'w-full max-w-md md:w-[22rem]' : 'w-10'"
      >
        <button
          type="button"
          class="relative flex h-10 shrink-0 items-center justify-center gap-1 border-b border-surface-border text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200"
          :title="sidebarOpen ? '收起侧栏' : '展开文件正文侧栏'"
          @click="toggleSidebar"
        >
          <span class="text-base leading-none">{{ sidebarOpen ? '›' : '‹' }}</span>
          <span v-if="sidebarOpen" class="font-medium text-emerald-300/90">文件正文</span>
          <span
            v-if="!sidebarOpen && hasBody"
            class="absolute right-1 top-2 h-2 w-2 rounded-full bg-emerald-400"
            title="已附带正文"
          />
        </button>

        <div v-show="sidebarOpen" class="flex min-h-0 flex-1 flex-col overflow-hidden">
          <div class="shrink-0 border-b border-surface-border bg-emerald-500/5 px-3 py-2">
            <p class="text-[11px] leading-relaxed text-slate-500">
              附件正文独立发送、不进路由模型。有正文时后端只允许写入文件；路径由下方自然语言说明。
            </p>
          </div>

          <div class="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-3 scrollbar-thin">
            <label class="flex min-h-0 flex-1 flex-col">
              <span class="mb-1 flex shrink-0 items-center justify-between text-[11px] text-slate-400">
                <span>正文内容（可选）</span>
                <span v-if="hasBody" class="text-emerald-400/80">{{ fileContent.length }} 字符</span>
              </span>
              <textarea
                v-model="fileContent"
                class="min-h-[14rem] flex-1 resize-y rounded-lg border border-surface-border bg-surface px-2.5 py-2 font-mono text-xs leading-relaxed text-slate-200 outline-none focus:ring-1 focus:ring-emerald-500/40"
                placeholder="粘贴或加载文件内容；发送时描述目标路径，如「写入 workspace/app.py」"
              />
            </label>

            <div class="flex shrink-0 flex-wrap gap-2">
              <button
                type="button"
                class="rounded-lg bg-surface px-3 py-1.5 text-xs text-slate-200 ring-1 ring-surface-border hover:bg-white/5"
                @click="onPickFile"
              >
                加载本地文件…
              </button>
              <button
                v-if="hasBody"
                type="button"
                class="rounded-lg px-3 py-1.5 text-xs text-slate-400 hover:bg-white/5 hover:text-slate-200"
                @click="clearBody"
              >
                清空
              </button>
              <input ref="fileInput" type="file" class="hidden" @change="onFileSelected" />
            </div>

            <p class="shrink-0 text-[10px] leading-relaxed text-slate-600">
              也可在消息里用 ``` 代码块代替侧栏。
            </p>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
