<script setup>
import { computed, ref, watch } from 'vue'
import { respondMessage, sendMessageLocal } from '../api/client.js'
import ChatInput from './ChatInput.vue'
import MessageItem from './MessageItem.vue'
import {
  buildSecurityAutoApproveAllMessage,
  securityApprovalHistory,
  securityChatMessages,
  securityPendingApprovals,
  securityYellowLogs,
  sortMessagesAsc,
} from '../utils/messages.js'
import { useChatScroll } from '../utils/useChatScroll.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

const emit = defineEmits(['send', 'responded', 'error'])

const autoApprove = ref(false)
const autoProcessing = ref(false)
const selectedApprovalId = ref(null)
const reason = ref('')
const submitting = ref(false)

const pendingList = computed(() => securityPendingApprovals(props.messages, props.agent))
const yellowLogs = computed(() => securityYellowLogs(props.messages, props.agent))
const approvalHistory = computed(() => securityApprovalHistory(props.messages, props.agent))
const chatOnly = computed(() => sortMessagesAsc(securityChatMessages(props.messages, props.agent)))
const { listEl, scrollToBottom } = useChatScroll(chatOnly)

const selectedApproval = computed(() => {
  if (autoApprove.value) return null
  if (!selectedApprovalId.value) return pendingList.value[0] || null
  return pendingList.value.find((m) => m.id === selectedApprovalId.value) || pendingList.value[0] || null
})

watch(
  pendingList,
  (list) => {
    if (!list.length) {
      selectedApprovalId.value = null
      return
    }
    if (!autoApprove.value && !list.some((m) => m.id === selectedApprovalId.value)) {
      selectedApprovalId.value = list[0].id
    }
    if (autoApprove.value) {
      triggerAutoApproveAll()
    }
  },
  { deep: true },
)

watch(autoApprove, (enabled) => {
  if (enabled) {
    selectedApprovalId.value = null
    triggerAutoApproveAll()
  }
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

function commandOf(msg) {
  return msg?.message?.payload?.command || msg?.message?.text || ''
}

function purposeOf(msg) {
  return msg?.message?.payload?.purpose || ''
}

async function submitApproval(approved) {
  const msg = selectedApproval.value
  if (!msg || submitting.value || autoApprove.value) return
  submitting.value = true
  try {
    const result = await respondMessage(msg.id, approved, reason.value)
    emit('responded', result.message)
    reason.value = ''
  } catch (e) {
    emit('error', e.message)
  } finally {
    submitting.value = false
  }
}

async function triggerAutoApproveAll() {
  if (!autoApprove.value || autoProcessing.value || !pendingList.value.length) return
  autoProcessing.value = true
  try {
    const msg = buildSecurityAutoApproveAllMessage(props.agent.id)
    await sendMessageLocal(msg)
  } catch (e) {
    emit('error', e.message)
    autoApprove.value = false
  } finally {
    autoProcessing.value = false
  }
}

async function onSend(text) {
  scrollToBottom(false)
  emit('send', text)
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <div class="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-2">
      <!-- 左：待审批 + 黄色记录 -->
      <div class="flex min-h-0 flex-col gap-3">
        <section class="flex min-h-0 flex-1 flex-col rounded-xl border border-surface-border bg-surface-elevated/40">
          <header class="border-b border-surface-border px-3 py-2">
            <div class="flex items-center justify-between gap-2">
              <span class="text-sm font-semibold text-amber-200">待审批（{{ pendingList.length }}）</span>
              <label
                class="flex shrink-0 cursor-pointer items-center gap-2 text-xs text-slate-300"
                title="开启后由 llama3.2 自动处理全部待审批，无需手动点批准/拒绝"
              >
                <input
                  v-model="autoApprove"
                  type="checkbox"
                  class="rounded border-surface-border"
                  :disabled="autoProcessing"
                />
                模型自动审批
              </label>
            </div>
            <p v-if="autoApprove" class="mt-1 text-[11px] text-indigo-300/90">
              已开启：新待审批将由本地模型自动处理，不会进入右侧手动审批
              <span v-if="autoProcessing">（处理中…）</span>
            </p>
          </header>
          <ul class="min-h-0 flex-1 overflow-y-auto p-2 text-sm">
            <li v-if="!pendingList.length" class="px-2 py-4 text-center text-slate-500">暂无待审批</li>
            <li
              v-for="item in pendingList"
              :key="item.id"
              class="mb-1 rounded-lg border px-3 py-2 transition"
              :class="
                autoApprove
                  ? 'border-indigo-500/30 bg-indigo-500/5'
                  : selectedApproval?.id === item.id
                    ? 'cursor-pointer border-amber-500/60 bg-amber-500/10'
                    : 'cursor-pointer border-transparent bg-slate-800/50 hover:bg-slate-800'
              "
              @click="!autoApprove && (selectedApprovalId = item.id)"
            >
              <p class="truncate font-mono text-xs text-red-300">{{ commandOf(item) }}</p>
              <p class="mt-1 truncate text-xs text-slate-500">{{ formatTime(item.timestamp) }}</p>
            </li>
          </ul>
        </section>

        <section class="flex max-h-48 min-h-0 flex-col rounded-xl border border-surface-border bg-surface-elevated/40 lg:max-h-none lg:flex-1">
          <header class="border-b border-surface-border px-3 py-2 text-sm font-semibold text-yellow-200">
            黄色记录
          </header>
          <ul class="min-h-0 flex-1 overflow-y-auto p-2 text-xs">
            <li v-if="!yellowLogs.length" class="px-2 py-4 text-center text-slate-500">暂无黄色记录</li>
            <li
              v-for="item in yellowLogs"
              :key="item.id"
              class="mb-2 rounded-lg bg-yellow-500/5 px-3 py-2 text-slate-300"
            >
              <p class="font-mono text-yellow-200/90">{{ item.message?.payload?.command || item.message?.text }}</p>
              <p class="mt-1 text-slate-500">
                {{ item.message?.payload?.rule_reason }}
                <span v-if="item.message?.payload?.escalated" class="text-red-400"> → 已升红</span>
              </p>
            </li>
          </ul>
        </section>
      </div>

      <!-- 右：审批界面 + 审批历史 -->
      <div class="flex min-h-0 flex-col gap-3">
        <section class="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
          <header class="mb-3 text-sm font-semibold text-amber-200">审批界面</header>

          <template v-if="autoApprove">
            <p class="py-6 text-center text-sm text-indigo-200/90">
              模型自动审批已开启<br />
              <span class="text-xs text-slate-400">待审批项由左侧开关统一处理，此处无需手动操作</span>
            </p>
          </template>

          <template v-else-if="selectedApproval">
            <p v-if="purposeOf(selectedApproval)" class="mb-2 text-sm text-slate-300">
              目的：{{ purposeOf(selectedApproval) }}
            </p>
            <pre class="mb-3 overflow-x-auto rounded-lg border border-red-500/30 bg-black/60 px-4 py-3 font-mono text-sm text-red-300">{{ commandOf(selectedApproval) }}</pre>
            <p class="mb-3 text-xs text-slate-500">{{ formatTime(selectedApproval.timestamp) }}</p>

            <input
              v-model="reason"
              type="text"
              placeholder="备注（可选）"
              class="mb-3 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
            />

            <div class="grid grid-cols-2 gap-3">
              <button
                type="button"
                class="rounded-xl bg-emerald-600 py-3 font-bold text-white transition hover:bg-emerald-500 disabled:opacity-50"
                :disabled="submitting"
                @click="submitApproval(true)"
              >
                ✓ 批准
              </button>
              <button
                type="button"
                class="rounded-xl bg-red-600 py-3 font-bold text-white transition hover:bg-red-500 disabled:opacity-50"
                :disabled="submitting"
                @click="submitApproval(false)"
              >
                ✕ 拒绝
              </button>
            </div>
          </template>
          <p v-else class="py-8 text-center text-sm text-slate-500">选择左侧待审批项，或等待新的审批请求</p>
        </section>

        <section class="flex min-h-0 flex-1 flex-col rounded-xl border border-surface-border bg-surface-elevated/40">
          <header class="border-b border-surface-border px-3 py-2 text-sm font-semibold text-slate-300">
            审批记录
          </header>
          <ul class="min-h-0 flex-1 overflow-y-auto p-2 text-xs">
            <li v-if="!approvalHistory.length" class="px-2 py-4 text-center text-slate-500">暂无审批记录</li>
            <li
              v-for="item in approvalHistory"
              :key="item.id"
              class="mb-2 rounded-lg bg-slate-800/60 px-3 py-2"
            >
              <div class="flex items-center justify-between gap-2">
                <span
                  class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold"
                  :class="
                    item.status === 'approved'
                      ? 'bg-emerald-500/20 text-emerald-300'
                      : item.status === 'rejected'
                        ? 'bg-red-500/20 text-red-300'
                        : 'bg-slate-600 text-slate-300'
                  "
                >
                  {{ item.status }}
                </span>
                <span class="truncate text-slate-500">{{ formatTime(item.timestamp) }}</span>
              </div>
              <p class="mt-1 truncate font-mono text-slate-300">{{ commandOf(item) }}</p>
              <p v-if="item.response?.reason" class="mt-1 text-slate-500">{{ item.response.reason }}</p>
            </li>
          </ul>
        </section>
      </div>
    </div>

    <!-- 底部对话 -->
    <div class="flex max-h-64 min-h-0 shrink-0 flex-col border-t border-surface-border">
      <div ref="listEl" class="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        <p v-if="!chatOnly.length" class="py-4 text-center text-xs text-slate-500">
          有待审批时以当前项为上下文；否则使用近期记录
        </p>
        <div v-for="msg in chatOnly" :key="msg.id" class="mb-2">
          <MessageItem :msg="msg" :agent="agent" @responded="(m) => emit('responded', m)" />
        </div>
      </div>
      <ChatInput @send="onSend" />
    </div>
  </div>
</template>
