<script setup>
import { computed, ref } from 'vue'
import MessageItem from './MessageItem.vue'
import {
  buildCrawlFileText,
  crawlResultFromMessage,
  crawlerJobMessages,
  downloadTextFile,
  requestCrawl,
  suggestCrawlFilename,
} from '../utils/crawler.js'
import { sortMessagesAsc } from '../utils/messages.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

const emit = defineEmits(['error', 'message'])

const url = ref('https://example.com')
const task = ref('抓取并提取页面有效正文')
const verifySsl = ref(true)
const useModel = ref(true)
/** 进行中的任务数（支持并行） */
const pendingCount = ref(0)
/** 新完成的任务是否自动刷新右侧；点选历史后为 false */
const followLatest = ref(true)
const errorText = ref('')
/** @type {import('vue').Ref<object|null>} */
const lastResult = ref(null)
const saveHint = ref('')

const jobLogs = computed(() => crawlerJobMessages(props.messages, props.agent, 30))
const timeline = computed(() => sortMessagesAsc(jobLogs.value).reverse())
const isRunningView = computed(() => lastResult.value?.status === 'running')

const filteredContent = computed(() => {
  const result = lastResult.value?.result
  return String(result?.content || '').trim()
})

const canSave = computed(() => Boolean(filteredContent.value) && !isRunningView.value)

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function preview(text, limit = 72) {
  const one = String(text || '').replace(/\n/g, ' ').trim()
  return one.length > limit ? `${one.slice(0, limit)}…` : one
}

function selectFromMessage(msg) {
  followLatest.value = false
  errorText.value = ''
  saveHint.value = ''

  if (msg.message?.status === 'running') {
    lastResult.value = {
      requestId: msg.message?.request_id || '',
      jobId: '',
      status: 'running',
      summary: msg.message?.summary || '爬取进行中',
      log: Array.isArray(msg.message?.log) ? msg.message.log : [],
      result: null,
      success: false,
      timestamp: msg.timestamp,
      messageId: msg.id,
    }
    return
  }

  const parsed = crawlResultFromMessage(msg)
  if (!parsed) {
    errorText.value = '无法打开该任务结果'
    return
  }
  lastResult.value = parsed
  if (!parsed.success && !parsed.result?.content) {
    errorText.value = parsed.summary || '爬取失败'
  }
}

async function onCrawl() {
  const target = url.value.trim()
  if (!target) {
    errorText.value = '请填写 URL'
    return
  }
  try {
    // eslint-disable-next-line no-new
    new URL(target)
  } catch {
    errorText.value = 'URL 格式无效'
    return
  }

  followLatest.value = true
  errorText.value = ''
  saveHint.value = ''
  pendingCount.value += 1

  try {
    const body = await requestCrawl(
      () => props.messages,
      props.agent.id,
      {
        url: target,
        task: task.value.trim(),
        use_model: useModel.value,
        config: { verify_ssl: verifySsl.value },
      },
      {
        onSent: (m) => emit('message', m),
      },
    )
    if (followLatest.value) {
      lastResult.value = body
      if (!body?.success) {
        errorText.value = body?.summary || '爬取失败'
        emit('error', errorText.value)
      } else {
        errorText.value = ''
      }
    }
  } catch (e) {
    if (followLatest.value) {
      errorText.value = e.message || '爬取失败'
      emit('error', errorText.value)
    }
  } finally {
    pendingCount.value = Math.max(0, pendingCount.value - 1)
  }
}

function onSaveFile() {
  if (!canSave.value) return
  const result = lastResult.value?.result
  const text = buildCrawlFileText(result)
  const filename = suggestCrawlFilename(result)
  downloadTextFile(text, filename)
  saveHint.value = `已下载：${filename}`
}

function onCopyContent() {
  if (!canSave.value) return
  const text = buildCrawlFileText(lastResult.value?.result)
  navigator.clipboard?.writeText(text).then(
    () => {
      saveHint.value = '已复制到剪贴板'
    },
    () => {
      saveHint.value = '复制失败，请手动选择正文'
    },
  )
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div class="shrink-0 border-b border-surface-border bg-sky-500/5 px-4 py-2 md:px-5">
      <p class="text-xs font-medium text-sky-200">网页爬取</p>
      <p class="mt-0.5 text-[11px] text-slate-500">
        支持多任务并行；进行中也可点选已完成任务预览。正文可下载为 Markdown。
      </p>
    </div>

    <div class="flex min-h-0 flex-1 flex-col md:flex-row">
      <!-- 左：表单 -->
      <section class="flex min-h-0 min-w-0 flex-1 flex-col border-b border-surface-border md:border-b-0 md:border-r">
        <div class="shrink-0 border-b border-surface-border px-4 py-2 md:px-5">
          <p class="text-xs font-medium text-slate-300">任务</p>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3 scrollbar-thin md:px-5">
          <label class="block text-xs text-slate-500">URL</label>
          <input
            v-model="url"
            type="url"
            class="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-sky-500/40"
            placeholder="https://example.com"
          />

          <label class="mt-3 block text-xs text-slate-500">任务描述（可选）</label>
          <textarea
            v-model="task"
            rows="3"
            class="mt-1 w-full resize-y rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-sky-500/40"
            placeholder="例如：提取正文，忽略导航与广告"
          />

          <div class="mt-3 flex flex-wrap gap-4 text-sm text-slate-300">
            <label class="inline-flex items-center gap-2">
              <input v-model="useModel" type="checkbox" class="rounded border-surface-border" />
              使用模型择优 / 提炼
            </label>
            <label class="inline-flex items-center gap-2">
              <input v-model="verifySsl" type="checkbox" class="rounded border-surface-border" />
              校验 SSL 证书
            </label>
          </div>

          <p class="mt-3 text-[11px] leading-relaxed text-slate-500">
            流水线：自适应引擎（RSS / 静态页 / Playwright）→ 过滤器 → 可选模型择优。后端最多同时跑 5
            个，超出排队。
          </p>

          <div class="mt-4 border-t border-surface-border pt-3">
            <p class="mb-2 text-xs font-medium text-slate-400">近期任务</p>
            <p class="mb-2 text-[11px] text-slate-500">每次爬取一条记录（进行中会在完成后更新）</p>
            <p v-if="!timeline.length" class="text-xs text-slate-500">暂无记录</p>
            <ul v-else class="space-y-1.5">
              <li
                v-for="msg in timeline"
                :key="msg.id"
                class="cursor-pointer rounded-lg border px-3 py-2 hover:border-sky-500/30"
                :class="
                  lastResult?.messageId === msg.id ||
                  (lastResult?.requestId && lastResult.requestId === msg.message?.request_id)
                    ? 'border-sky-500/40 bg-sky-500/10'
                    : 'border-surface-border bg-surface-raised/40'
                "
                @click="selectFromMessage(msg)"
              >
                <div class="flex items-start justify-between gap-2">
                  <p class="min-w-0 flex-1 truncate text-sm text-slate-200">
                    {{ msg.message?.summary || '爬取任务' }}
                  </p>
                  <span
                    class="shrink-0 text-[10px]"
                    :class="{
                      'text-amber-400': msg.message?.status === 'running',
                      'text-emerald-400': msg.message?.status === 'completed',
                      'text-red-400': msg.message?.status === 'failed',
                      'text-slate-500': !msg.message?.status,
                    }"
                  >
                    {{ msg.message?.status || '—' }}
                  </span>
                </div>
                <p class="mt-0.5 text-[11px] text-slate-500">{{ formatTime(msg.timestamp) }}</p>
                <p
                  v-if="msg.message?.payload?.result?.content"
                  class="mt-1 truncate text-[11px] text-slate-400"
                >
                  {{ preview(msg.message.payload.result.content) }}
                </p>
              </li>
            </ul>
          </div>
        </div>

        <div class="shrink-0 border-t border-surface-border px-4 py-3 md:px-5">
          <button
            type="button"
            class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
            :disabled="loading"
            @click="onCrawl"
          >
            {{ pendingCount > 0 ? `再添加任务（${pendingCount} 进行中）` : '开始爬取' }}
          </button>
          <p v-if="errorText" class="mt-2 text-xs text-red-300">{{ errorText }}</p>
        </div>
      </section>

      <!-- 右：结果 -->
      <section class="flex min-h-0 min-w-0 flex-1 flex-col">
        <div class="shrink-0 border-b border-surface-border px-4 py-2 md:px-5">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="min-w-0">
              <p class="text-xs font-medium text-slate-300">过滤后内容</p>
              <p v-if="pendingCount > 0" class="mt-0.5 text-[11px] text-amber-400/90">
                {{ pendingCount }} 个任务进行中（点左侧可查看其它已完成结果）
              </p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                type="button"
                class="rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 hover:bg-surface-raised disabled:opacity-40"
                :disabled="!canSave"
                @click="onCopyContent"
              >
                复制
              </button>
              <button
                type="button"
                class="rounded-md bg-sky-600/90 px-2.5 py-1 text-xs text-white hover:bg-sky-500 disabled:opacity-40"
                :disabled="!canSave"
                @click="onSaveFile"
              >
                保存为文件
              </button>
            </div>
          </div>
          <p v-if="saveHint" class="mt-1 text-[11px] text-emerald-400/90">{{ saveHint }}</p>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3 scrollbar-thin md:px-5">
          <div v-if="lastResult" class="space-y-3">
            <div
              class="rounded-xl border px-4 py-3"
              :class="{
                'border-amber-500/30 bg-amber-500/5': isRunningView,
                'border-emerald-500/30 bg-emerald-500/5': !isRunningView && lastResult.success,
                'border-red-500/30 bg-red-500/5': !isRunningView && !lastResult.success,
              }"
            >
              <p class="text-sm text-slate-200">
                {{
                  lastResult.summary ||
                  (isRunningView ? '进行中' : lastResult.success ? '完成' : '失败')
                }}
              </p>
              <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-slate-500">
                <span v-if="lastResult.jobId">job: {{ lastResult.jobId }}</span>
                <span v-if="lastResult.result?.strategy">引擎: {{ lastResult.result.strategy }}</span>
                <span v-if="lastResult.result?.picked_filter">
                  过滤: {{ lastResult.result.picked_filter }}
                </span>
                <span v-if="lastResult.result?.url" class="truncate">{{ lastResult.result.url }}</span>
              </div>
            </div>

            <div
              v-if="isRunningView"
              class="flex h-32 items-center justify-center text-sm text-slate-500"
            >
              该任务仍在爬取中…
            </div>

            <template v-else>
              <div v-if="lastResult.result?.title" class="text-sm font-medium text-slate-200">
                {{ lastResult.result.title }}
              </div>

              <pre
                v-if="filteredContent"
                class="max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-xl border border-surface-border bg-black/30 px-3 py-3 font-mono text-xs leading-relaxed text-slate-300 scrollbar-thin"
              >{{ filteredContent }}</pre>
              <p v-else class="text-sm text-slate-500">无过滤正文可保存</p>

              <details v-if="lastResult.log?.length" class="rounded-lg border border-surface-border">
                <summary class="cursor-pointer px-3 py-2 text-xs text-slate-400 hover:bg-white/5">
                  执行日志（{{ lastResult.log.length }} 行）
                </summary>
                <pre
                  class="max-h-48 overflow-auto border-t border-surface-border bg-black px-3 py-2 font-mono text-[10px] leading-relaxed text-emerald-400/90"
                >{{ lastResult.log.join('\n') }}</pre>
              </details>
            </template>
          </div>

          <div v-else class="space-y-3">
            <p class="py-6 text-center text-sm text-slate-500">
              填写 URL 后点击「开始爬取」，或从左侧近期任务打开结果
            </p>
            <div v-if="timeline.length" class="mx-auto flex max-w-xl flex-col gap-3">
              <MessageItem v-for="msg in timeline.slice(0, 5)" :key="msg.id" :msg="msg" />
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
