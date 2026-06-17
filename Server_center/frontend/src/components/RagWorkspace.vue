<script setup>
import { computed, ref } from 'vue'
import { sendMessageLocal } from '../api/client.js'
import ChatInput from './ChatInput.vue'
import MessageItem from './MessageItem.vue'
import {
  buildRagIngestTextMessage,
  ragChatMessages,
  ragIngestLogs,
  sortMessagesAsc,
} from '../utils/messages.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

const emit = defineEmits(['send', 'responded', 'ingested', 'error'])

const SPLIT_MODES = [
  { value: 'rule', label: '① 规则贪婪合并（快）' },
  { value: 'semantic', label: '② 3B 语义裁判' },
  { value: 'semantic_embedding', label: '③ 向量断点' },
  { value: 'structural', label: '④ 文档结构（推荐 .md）' },
]

const TEXT_SUFFIXES = ['.txt', '.md', '.markdown', '.json', '.csv', '.log', '.py', '.js', '.ts', '.html', '.xml', '.yaml', '.yml']

const collectionId = ref('default')
const splitMode = ref('rule')
const ingestTitle = ref('')
const ingestText = ref('')
const ingestBusy = ref(false)
const ingestError = ref('')
const fileInput = ref(null)

const chatOnly = computed(() => sortMessagesAsc(ragChatMessages(props.messages, props.agent)))
const ingestLogs = computed(() => ragIngestLogs(props.messages, props.agent))

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

async function submitIngest(text, title) {
  const body = text.trim()
  if (!body) {
    ingestError.value = '内容不能为空'
    return
  }
  if (body.length > 500_000) {
    ingestError.value = '内容过大（>500KB），请拆分后入库'
    return
  }

  ingestBusy.value = true
  ingestError.value = ''
  try {
    const msg = buildRagIngestTextMessage(props.agent.id, {
      text: body,
      title: title || ingestTitle.value.trim() || 'web_upload',
      collection_id: collectionId.value.trim() || 'default',
      split_mode: splitMode.value,
    })
    const result = await sendMessageLocal(msg)
    emit('ingested', result.message)
    ingestText.value = ''
    ingestTitle.value = ''
  } catch (e) {
    ingestError.value = e.message
    emit('error', e.message)
  } finally {
    ingestBusy.value = false
  }
}

async function onIngestText() {
  await submitIngest(ingestText.value, ingestTitle.value.trim() || undefined)
}

function onPickFile() {
  fileInput.value?.click()
}

async function onFileSelected(event) {
  const file = event.target.files?.[0]
  if (!file) return

  const lower = file.name.toLowerCase()
  if (!TEXT_SUFFIXES.some((s) => lower.endsWith(s))) {
    ingestError.value = `不支持该文件类型，仅支持：${TEXT_SUFFIXES.join(', ')}`
    event.target.value = ''
    return
  }

  try {
    const text = await file.text()
    await submitIngest(text, file.name)
  } catch (e) {
    ingestError.value = e.message || '读取文件失败'
  } finally {
    event.target.value = ''
  }
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col md:flex-row">
    <!-- 左：对话 -->
    <section class="flex min-h-0 min-w-0 flex-1 flex-col border-b border-surface-border md:w-1/2 md:border-b-0 md:border-r">
      <div class="shrink-0 border-b border-surface-border bg-violet-500/5 px-4 py-2 md:px-5">
        <p class="text-xs font-medium text-violet-300">对话检索</p>
        <p class="text-[11px] text-slate-500">向 RAG 模块提问，基于向量库召回并回答</p>
      </div>

      <div class="flex-1 overflow-y-auto px-3 py-3 scrollbar-thin md:px-5">
        <div v-if="loading" class="flex h-32 items-center justify-center text-sm text-slate-500">加载中…</div>
        <p v-else-if="!chatOnly.length" class="py-10 text-center text-sm text-slate-500">
          在下方输入问题，例如「文档里如何创建 Git 仓库？」
        </p>
        <div v-else class="mx-auto flex max-w-xl flex-col gap-3">
          <MessageItem
            v-for="msg in chatOnly"
            :key="msg.id"
            :msg="msg"
            @responded="emit('responded', $event)"
          />
        </div>
      </div>

      <ChatInput @send="(text, att) => emit('send', text, att)" />
    </section>

    <!-- 右：入库 -->
    <section class="flex min-h-0 min-w-0 flex-1 flex-col md:w-1/2">
      <div class="shrink-0 border-b border-surface-border bg-emerald-500/5 px-4 py-2 md:px-5">
        <p class="text-xs font-medium text-emerald-300">知识库入库</p>
        <p class="text-[11px] text-slate-500">粘贴文本或上传文件到 Local Agent 向量库</p>
      </div>

      <div class="flex-1 overflow-y-auto px-4 py-3 scrollbar-thin md:px-5">
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-2">
            <label class="block">
              <span class="mb-1 block text-[11px] text-slate-400">Collection</span>
              <input
                v-model="collectionId"
                type="text"
                class="w-full rounded-lg border border-surface-border bg-surface-raised px-2.5 py-1.5 text-sm text-slate-200 outline-none ring-violet-500/40 focus:ring-1"
                placeholder="default"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] text-slate-400">分块方式</span>
              <select
                v-model="splitMode"
                class="w-full rounded-lg border border-surface-border bg-surface-raised px-2 py-1.5 text-sm text-slate-200 outline-none ring-violet-500/40 focus:ring-1"
              >
                <option v-for="m in SPLIT_MODES" :key="m.value" :value="m.value">{{ m.label }}</option>
              </select>
            </label>
          </div>

          <label class="block">
            <span class="mb-1 block text-[11px] text-slate-400">标题（可选）</span>
            <input
              v-model="ingestTitle"
              type="text"
              class="w-full rounded-lg border border-surface-border bg-surface-raised px-2.5 py-1.5 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-violet-500/40"
              placeholder="例如 README 摘要"
            />
          </label>

          <label class="block">
            <span class="mb-1 block text-[11px] text-slate-400">粘贴文本</span>
            <textarea
              v-model="ingestText"
              rows="6"
              class="w-full resize-y rounded-lg border border-surface-border bg-surface-raised px-2.5 py-2 font-mono text-xs leading-relaxed text-slate-200 outline-none focus:ring-1 focus:ring-violet-500/40"
              placeholder="在此粘贴要入库的文档内容…"
            />
          </label>

          <p v-if="ingestError" class="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-300">{{ ingestError }}</p>

          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-lg bg-violet-600 px-4 py-2 text-sm text-white hover:bg-violet-500 disabled:opacity-50"
              :disabled="ingestBusy"
              @click="onIngestText"
            >
              {{ ingestBusy ? '入库中…' : '入库文本' }}
            </button>
            <button
              type="button"
              class="rounded-lg bg-surface-raised px-4 py-2 text-sm text-slate-200 ring-1 ring-surface-border hover:bg-white/5 disabled:opacity-50"
              :disabled="ingestBusy"
              @click="onPickFile"
            >
              选择文件…
            </button>
            <input
              ref="fileInput"
              type="file"
              class="hidden"
              accept=".txt,.md,.markdown,.json,.csv,.log,.py,.js,.ts,.html,.xml,.yaml,.yml"
              @change="onFileSelected"
            />
          </div>

          <div class="border-t border-surface-border pt-3">
            <p class="mb-2 text-xs font-medium text-slate-400">入库记录</p>
            <p v-if="!ingestLogs.length" class="text-xs text-slate-500">暂无入库记录，完成入库后会显示 execution_log</p>
            <ul v-else class="space-y-2">
              <li
                v-for="log in ingestLogs"
                :key="log.id"
                class="rounded-lg border border-surface-border bg-black/20 px-3 py-2"
              >
                <p class="text-sm text-slate-200">{{ log.message?.summary || '入库' }}</p>
                <p class="mt-0.5 text-[11px] text-slate-500">{{ formatTime(log.timestamp) }}</p>
                <ul v-if="log.message?.log?.length" class="mt-1 space-y-0.5 font-mono text-[10px] text-slate-500">
                  <li v-for="(line, i) in log.message.log" :key="i">{{ line }}</li>
                </ul>
                <p v-if="log.message?.payload?.split_mode" class="mt-1 text-[10px] text-violet-400/80">
                  split_mode: {{ log.message.payload.split_mode }}
                  · chunks: {{ log.message.payload.chunk_count }}
                </p>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
