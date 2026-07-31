<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { sendMessageLocal } from '../../api/client.js'
import { makeUserMessageId } from '../../utils/messages.js'
import TaskGraphCanvas from '../planning/TaskGraphCanvas.vue'

const OTHER_LABEL = '其他'
const KIND_LABEL = {
  goal: '目标',
  env: '环境',
  process: '处理',
  action: '执行',
}
const STATUS_LABEL = {
  pending: '等待',
  running: '执行中',
  succeeded: '成功',
  failed: '失败',
  skipped: '跳过',
}

const props = defineProps({
  msg: { type: Object, required: true },
})

const emit = defineEmits(['responded', 'action'])

const submitting = ref(false)
const cancelling = ref(false)
const selectedNodeId = ref('')

const body = computed(() => props.msg.message || {})
const questions = computed(() => (Array.isArray(body.value.questions) ? body.value.questions : []))
const graph = computed(() => body.value.graph || null)
const nodeStatus = computed(() => body.value.node_status || {})
const phase = computed(() => body.value.phase || body.value.status || '')
const clarifying = computed(() => phase.value === 'clarifying' && questions.value.length > 0)
const canCancel = computed(
  () =>
    body.value.can_cancel !== false &&
    !['done', 'failed', 'cancelled', 'succeeded'].includes(phase.value),
)

const phaseLabel = computed(() => {
  const p = phase.value
  if (p === 'collecting') return '收集信息'
  if (p === 'clarifying') return '等待质询'
  if (p === 'probing') return '环境探测'
  if (p === 'planning') return '生成任务图'
  if (p === 'running') return '执行中'
  if (p === 'done' || p === 'succeeded') return '已完成'
  if (p === 'failed') return '失败'
  if (p === 'cancelled') return '已取消'
  return p || '规划'
})

const statusClass = computed(() => {
  const p = phase.value
  if (p === 'failed' || body.value.ok === false) return 'bg-red-500/20 text-red-300'
  if (p === 'cancelled') return 'bg-slate-500/20 text-slate-300'
  if (p === 'done' || p === 'succeeded') return 'bg-emerald-500/20 text-emerald-300'
  if (p === 'clarifying') return 'bg-sky-500/20 text-sky-200'
  if (['running', 'collecting', 'probing', 'planning'].includes(p)) return 'bg-amber-500/20 text-amber-200'
  return 'bg-slate-500/20 text-slate-300'
})

/** @type {import('vue').Reactive<Record<string, { choice: string, other: string }>>} */
const answers = reactive({})

function ensureAnswer(qid) {
  if (!answers[qid]) answers[qid] = { choice: '', other: '' }
  return answers[qid]
}

watch(
  questions,
  (list) => {
    for (const q of list) ensureAnswer(q.id)
  },
  { immediate: true },
)

function resolvedAnswer(q) {
  const state = ensureAnswer(q.id)
  if (state.choice === OTHER_LABEL) return (state.other || '').trim()
  return (state.choice || '').trim()
}

function allAnswered() {
  return questions.value.every((q) => resolvedAnswer(q))
}

async function sendAction(action, extra = {}) {
  const payload = {
    id: makeUserMessageId(),
    name: 'user_ui',
    target: 'main',
    msg_type: 'planning_action',
    message: {
      action,
      session_id: body.value.session_id || 'default',
      request_id: body.value.request_id || '',
      ...extra,
    },
    timestamp: Math.floor(Date.now() / 1000),
  }
  const result = await sendMessageLocal(payload)
  emit('action', result.message)
  return result
}

async function submitClarify() {
  if (!allAnswered() || submitting.value) return
  submitting.value = true
  try {
    await sendAction('clarify', {
      answers: questions.value.map((q) => ({
        question_id: q.id,
        answer: resolvedAnswer(q),
        question: q.prompt || '',
      })),
    })
  } catch (e) {
    alert(e.message)
  } finally {
    submitting.value = false
  }
}

async function cancelPlan() {
  if (!canCancel.value || cancelling.value) return
  cancelling.value = true
  try {
    await sendAction('cancel')
  } catch (e) {
    alert(e.message)
  } finally {
    cancelling.value = false
  }
}

function onNodeClick(nodeId) {
  selectedNodeId.value = selectedNodeId.value === nodeId ? '' : nodeId
}

const selectedNode = computed(() => {
  const id = selectedNodeId.value
  if (!id || !graph.value?.nodes) return null
  const node = graph.value.nodes.find((n) => n.id === id)
  const st = nodeStatus.value[id] || {}
  return { id, node, status: st }
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function nodeCaption(node) {
  if (!node) return ''
  if (node.kind === 'process') return node.requirement || ''
  return node.instruction || ''
}
</script>

<template>
  <div class="w-full max-w-2xl">
    <div class="rounded-xl border border-sky-500/30 bg-sky-500/5 px-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium text-sky-300">任务规划</p>
        <div class="flex items-center gap-2">
          <span class="rounded px-1.5 py-0.5 text-[10px] tracking-wide" :class="statusClass">
            {{ phaseLabel }}
          </span>
          <button
            v-if="canCancel"
            type="button"
            class="rounded border border-slate-500/40 px-2 py-0.5 text-[10px] text-slate-400 hover:border-red-400/50 hover:text-red-300 disabled:opacity-40"
            :disabled="cancelling"
            @click="cancelPlan"
          >
            取消
          </button>
        </div>
      </div>

      <p v-if="body.error && (phase === 'failed' || phase === 'cancelled')" class="mt-2 text-sm text-red-300">
        {{ body.error }}
      </p>

      <p v-if="body.goal" class="mt-2 whitespace-pre-wrap text-sm font-medium text-slate-200">
        目标：{{ body.goal }}
      </p>
      <p v-if="body.summary" class="mt-2 text-sm text-slate-300">{{ body.summary }}</p>
      <p v-else-if="body.text && !graph?.nodes?.length && !clarifying" class="mt-2 text-sm text-slate-400">
        {{ body.text }}
      </p>

      <!-- 质询 -->
      <div v-if="clarifying" class="mt-3 space-y-4 rounded-lg border border-sky-500/20 bg-slate-950/40 p-3">
        <p class="text-xs font-medium text-sky-300">需要补充信息</p>
        <div v-for="q in questions" :key="q.id" class="space-y-2">
          <p class="text-sm font-medium text-slate-200">{{ q.prompt }}</p>
          <p v-if="q.reason" class="text-xs text-slate-500">原因：{{ q.reason }}</p>
          <label
            v-for="(c, i) in [...(q.choices || []), OTHER_LABEL]"
            :key="`${q.id}-${i}`"
            class="flex cursor-pointer items-center gap-2 text-sm text-slate-300"
          >
            <input
              v-model="ensureAnswer(q.id).choice"
              type="radio"
              class="accent-sky-500"
              :value="c"
              :disabled="submitting"
            />
            {{ c }}
          </label>
          <input
            v-if="ensureAnswer(q.id).choice === OTHER_LABEL"
            v-model="ensureAnswer(q.id).other"
            type="text"
            placeholder="自行输入…"
            class="mt-1 w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
            :disabled="submitting"
          />
        </div>
        <button
          type="button"
          class="w-full rounded-xl bg-sky-600 py-2.5 text-sm font-semibold text-white hover:bg-sky-500 disabled:opacity-50"
          :disabled="submitting || !allAnswered()"
          @click="submitClarify"
        >
          提交回答
        </button>
      </div>

      <!-- 任务图 -->
      <div
        v-if="graph?.nodes?.length"
        class="mt-3 overflow-hidden rounded-lg border border-sky-500/20 bg-slate-950/40"
      >
        <TaskGraphCanvas
          :graph="graph"
          :node-status="nodeStatus"
          compact
          @node-click="onNodeClick"
        />
      </div>

      <!-- 节点详情 -->
      <div
        v-if="selectedNode"
        class="mt-2 rounded-lg border border-edge bg-slate-900/70 px-3 py-2 text-xs text-slate-300"
      >
        <p class="font-medium text-slate-200">
          {{ selectedNode.id }}
          <span
            v-if="selectedNode.node?.kind"
            class="ml-2 rounded px-1.5 py-0.5 text-[10px]"
            :class="
              selectedNode.node.kind === 'process'
                ? 'bg-teal-500/20 text-teal-300'
                : selectedNode.node.kind === 'action'
                  ? 'bg-orange-500/20 text-orange-300'
                  : 'bg-slate-500/20 text-slate-300'
            "
          >
            {{ KIND_LABEL[selectedNode.node.kind] || selectedNode.node.kind }}
          </span>
          <span class="ml-2 text-slate-500">
            {{ STATUS_LABEL[selectedNode.status.status] || selectedNode.status.status || '—' }}
          </span>
        </p>
        <p v-if="selectedNode.node" class="mt-1 whitespace-pre-wrap text-slate-400">
          {{ nodeCaption(selectedNode.node) }}
        </p>
        <p v-if="selectedNode.status.detail || selectedNode.status.error" class="mt-1 text-amber-200/80">
          {{ selectedNode.status.detail || selectedNode.status.error }}
        </p>
        <p v-if="selectedNode.status.attempts" class="mt-1 text-slate-500">
          尝试次数：{{ selectedNode.status.attempts }}
        </p>
      </div>

      <p v-if="body.files?.length" class="mt-2 text-xs text-slate-500">
        产出文件 {{ body.files.length }} 个
      </p>
      <p class="mt-2 text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>
    </div>
  </div>
</template>
