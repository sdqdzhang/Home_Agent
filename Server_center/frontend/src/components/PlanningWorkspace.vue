<script setup>
import { computed, watch } from 'vue'
import TaskGraphCanvas from './planning/TaskGraphCanvas.vue'
import {
  OTHER_LABEL,
  MAX_COLLECT_ROUNDS,
  composeGoal,
  requestClarify,
  requestEnvProbe,
  requestPlan,
  requestRunGraph,
  PLAN_PROGRESS,
} from '../utils/planning.js'
import {
  STATUS,
  STATUS_LABEL,
  activePlanningSession,
  addPlanningSession,
  appendSessionLog,
  ensureActivePlanningSession,
  getPlanningSession,
  removePlanningSession,
  resetSessionCollection,
  selectPlanningSession,
  setSessionPhase,
  sortedPlanningSessions,
  touchSession,
} from '../utils/planningSessions.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

const emit = defineEmits(['error'])

ensureActivePlanningSession()

const session = activePlanningSession
const sessions = computed(() => sortedPlanningSessions())

const currentQuestion = computed(() => session.value?.pendingQuestions?.[0] || null)
const canRun = computed(() => !!session.value?.graph && !session.value?.busy)
const initialBlockLabels = computed(() =>
  (session.value?.envBlocks || []).map((b) => {
    const detail = String(b.metadata?.instruction || b.content || '').replace(/\s+/g, ' ')
    const short = detail.length > 60 ? `${detail.slice(0, 60)}…` : detail
    return { id: b.id, label: short ? `${b.id}  [env]\n${short}` : `${b.id}\n[env]` }
  }),
)

function getMessages() {
  return props.messages
}

function log(s, msg) {
  appendSessionLog(s, msg)
}

function clearClarifyPanels(s) {
  s.pendingQuestions = []
  s.pendingEnv = []
  s.envChecks = []
  s.choice = ''
  s.otherText = ''
  s.questionsDone = true
  s.envDone = true
}

function onNewTask() {
  addPlanningSession()
}

function onSelectTask(id) {
  selectPlanningSession(id)
}

function onRemoveTask(id, e) {
  e?.stopPropagation?.()
  const target = getPlanningSession(id)
  if (target?.busy) {
    emit('error', '任务进行中，无法删除')
    return
  }
  if (!window.confirm('删除该任务记录？进度将丢失。')) return
  removePlanningSession(id)
  ensureActivePlanningSession()
}

function onReset() {
  const s = session.value
  if (!s || s.busy) return
  resetSessionCollection(s, { keepGoal: true })
  log(s, '已重置本任务进度（保留目标）')
}

async function onStart() {
  const s = session.value
  if (!s || s.busy) return
  const g = s.goal.trim()
  if (!g) {
    emit('error', '请填写目标')
    return
  }
  resetSessionCollection(s, { keepGoal: true })
  s.goal = g
  touchSession(s)
  log(s, `目标: ${g}`)
  await beginClarifyRound(s.id)
}

async function beginClarifyRound(sessionId) {
  const s = getPlanningSession(sessionId)
  if (!s) return
  s.busy = true
  setSessionPhase(s, STATUS.collecting, `信息收集中…（第 ${s.roundIndex} 轮）`)
  log(s, `--- 信息收集 第 ${s.roundIndex} 轮（回答 ${s.history.length}｜探测 ${s.envRecords.length}）---`)
  try {
    const outcome = await requestClarify(getMessages, props.agent.id, {
      goal: s.goal.trim(),
      history: s.history,
      env_records: s.envRecords,
      round_index: s.roundIndex,
    })
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    if (outcome.note) log(cur, `note: ${outcome.note}`)
    if (outcome.ready) {
      log(cur, '信息已足够，开始生成任务图…')
      clearClarifyPanels(cur)
      await doPlan(sessionId)
      return
    }
    cur.pendingQuestions = [...(outcome.questions || [])]
    cur.pendingEnv = [...(outcome.env_queries || [])]
    cur.questionsDone = !cur.pendingQuestions.length
    cur.envDone = !cur.pendingEnv.length
    log(cur, `本轮：用户质询 ${cur.pendingQuestions.length} 题，环境探测 ${cur.pendingEnv.length} 条`)
    showEnvPanel(cur)
    showNextQuestion(cur)
    setSessionPhase(
      cur,
      STATUS.collecting,
      `请回答质询（${cur.pendingQuestions.length}）并批准探测（${cur.pendingEnv.length}）`,
    )
    cur.busy = false
  } catch (e) {
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    cur.busy = false
    setSessionPhase(cur, STATUS.failed, '信息收集异常')
    log(cur, String(e.message || e))
    emit('error', e.message || String(e))
  }
}

function showNextQuestion(s) {
  const q = s.pendingQuestions[0]
  if (!q) {
    s.questionsDone = true
    s.choice = ''
    s.otherText = ''
    maybeNextRound(s.id)
    return
  }
  s.questionsDone = false
  const choices = [...(q.choices || []), OTHER_LABEL]
  s.choice = choices[0] || ''
  s.otherText = ''
  s.statusText = `请回答：${q.id}（剩余 ${s.pendingQuestions.length} 题）`
  touchSession(s)
}

function showEnvPanel(s) {
  s.envChecks = (s.pendingEnv || []).map((q) => ({ q, checked: true }))
}

function toggleEnvAll() {
  const s = session.value
  if (!s?.envChecks?.length) return
  const target = !s.envChecks.every((x) => x.checked)
  s.envChecks = s.envChecks.map((x) => ({ ...x, checked: target }))
}

function submitAnswer() {
  const s = session.value
  if (!s || s.busy || !s.pendingQuestions[0]) return
  const q = s.pendingQuestions[0]
  let answer = s.choice
  if (answer === OTHER_LABEL) {
    answer = s.otherText.trim()
    if (!answer) {
      emit('error', '请填写「其他」内容')
      return
    }
  }
  if (!answer) {
    emit('error', '请选择一个选项')
    return
  }
  s.history = [...s.history, { question_id: q.id, question: q.prompt, answer }]
  log(s, `  [${q.id}] → ${answer}`)
  s.pendingQuestions = s.pendingQuestions.slice(1)
  showNextQuestion(s)
}

async function approveEnv() {
  const s = session.value
  if (!s || s.busy || !s.envChecks.length) return
  const sessionId = s.id
  const approved = []
  for (const { q, checked } of s.envChecks) {
    if (checked) {
      approved.push(q)
    } else {
      s.envRecords = [
        ...s.envRecords,
        {
          id: q.id,
          instruction: q.instruction,
          purpose: q.purpose || '',
          status: 'denied_user',
          block_id: '',
          summary: '用户未批准',
          round_index: s.roundIndex,
        },
      ]
      log(s, `  [env ${q.id}] 用户拒绝`)
    }
  }
  s.pendingEnv = []
  s.envChecks = []

  if (!approved.length) {
    log(s, '本轮环境探测：全部拒绝')
    s.envDone = true
    await maybeNextRound(sessionId)
    return
  }

  s.busy = true
  setSessionPhase(s, STATUS.collecting, `执行环境探测（${approved.length} 条）…`)
  const queries = approved.map((q) => {
    s.envSeq += 1
    return {
      id: q.id,
      instruction: q.instruction,
      purpose: q.purpose || '',
      block_id: `env${s.envSeq}`,
    }
  })
  try {
    const res = await requestEnvProbe(getMessages, props.agent.id, {
      queries,
      round_index: s.roundIndex,
    })
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    for (const item of res.results || []) {
      const rec = item.record
      if (rec) {
        cur.envRecords = [...cur.envRecords, rec]
        log(
          cur,
          `  [env ${rec.id}] ${rec.status} → ${rec.block_id || '-'} ${(rec.summary || '').slice(0, 60)}`,
        )
      }
      if (item.block) cur.envBlocks = [...cur.envBlocks, item.block]
    }
  } catch (e) {
    const cur = getPlanningSession(sessionId)
    if (cur) {
      log(cur, String(e.message || e))
    }
    emit('error', e.message || String(e))
  } finally {
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    cur.busy = false
    cur.envDone = true
    await maybeNextRound(sessionId)
  }
}

async function maybeNextRound(sessionId) {
  const s = getPlanningSession(sessionId)
  if (!s || s.busy) return
  if (s.pendingQuestions.length > 0) {
    s.questionsDone = false
    return
  }
  s.questionsDone = true
  if (!s.envDone) return
  if (s.envChecks.length > 0) return

  clearClarifyPanels(s)
  s.roundIndex += 1
  if (s.roundIndex > MAX_COLLECT_ROUNDS) {
    const cont = window.confirm(
      `已进行 ${MAX_COLLECT_ROUNDS} 轮信息收集。\n确定→继续收集；取消→用现有信息直接规划。`,
    )
    if (!cont) {
      log(s, '达到轮次上限，直接规划')
      await doPlan(sessionId)
      return
    }
    s.roundIndex = MAX_COLLECT_ROUNDS
  }
  await beginClarifyRound(sessionId)
}

async function doPlan(sessionId) {
  const s = getPlanningSession(sessionId)
  if (!s) return
  s.busy = true
  setSessionPhase(s, STATUS.planning, '规划中…')
  clearClarifyPanels(s)
  try {
    const plan = await requestPlan(getMessages, props.agent.id, {
      goal: s.goal.trim(),
      clarifications: s.history,
      context_blocks: s.envBlocks,
    })
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    if (!plan.ok || !plan.graph) {
      setSessionPhase(cur, STATUS.failed, '规划失败')
      log(cur, `规划失败: ${plan.error || '未知错误'}`)
      cur.jsonText = JSON.stringify(plan.raw || plan, null, 2)
      cur.tab = 'json'
      emit('error', plan.error || '规划失败')
      cur.busy = false
      return
    }
    cur.graph = plan.graph
    cur.nodeStatus = {}
    cur.jsonText = JSON.stringify(plan.graph, null, 2)
    log(cur, `任务图已生成，节点数=${plan.graph.nodes?.length || 0}`)
    if (plan.summary) log(cur, `summary: ${plan.summary}`)
    setSessionPhase(cur, STATUS.ready, '任务图就绪，可执行')
    cur.tab = 'graph'
  } catch (e) {
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    setSessionPhase(cur, STATUS.failed, '规划异常')
    log(cur, String(e.message || e))
    emit('error', e.message || String(e))
  } finally {
    const cur = getPlanningSession(sessionId)
    if (cur) cur.busy = false
  }
}

function applyProgressToSession(s) {
  if (!s?.runRequestId) return
  const progresses = props.messages.filter(
    (m) => m.msg_type === PLAN_PROGRESS && m.message?.request_id === s.runRequestId,
  )
  const next = { ...s.nodeStatus }
  for (const m of progresses) {
    const p = m.message
    if (!p?.node_id) continue
    next[p.node_id] = {
      status: p.status || 'pending',
      attempts: p.attempts || 0,
      error: p.error || '',
    }
  }
  s.nodeStatus = next
  touchSession(s)
}

async function onRun() {
  const s = session.value
  if (!s || !canRun.value || !s.graph) return
  const sessionId = s.id
  s.busy = true
  setSessionPhase(s, STATUS.running, '执行中…')
  log(s, '--- 执行任务图 ---')
  s.nodeStatus = {}
  const effective = composeGoal(s.goal.trim(), s.history)
  try {
    const { request_id, resultPromise } = await requestRunGraph(getMessages, props.agent.id, {
      goal: effective,
      graph: s.graph,
      initial_blocks: s.envBlocks,
    })
    const cur = getPlanningSession(sessionId)
    if (!cur) return
    cur.runRequestId = request_id
    const result = await resultPromise
    const live = getPlanningSession(sessionId)
    if (!live) return
    applyProgressToSession(live)
    for (const st of result.nodes || []) {
      live.nodeStatus = {
        ...live.nodeStatus,
        [st.node_id]: {
          status: st.status,
          attempts: st.attempts || 0,
          error: st.error || '',
        },
      }
      let line = `  [${st.status}] ${st.node_id} attempts=${st.attempts || 0} out=${st.output_block_id || '-'}`
      if (st.error) line += ` err=${st.error}`
      log(live, line)
    }
    log(live, `ok: ${result.ok}`)
    if (result.error) log(live, `error: ${result.error}`)
    live.jsonText = JSON.stringify(
      {
        ok: result.ok,
        error: result.error,
        nodes: result.nodes,
        blocks: result.blocks,
        skipped_node_ids: result.skipped_node_ids,
      },
      null,
      2,
    )
    live.tab = 'json'
    setSessionPhase(live, result.ok ? STATUS.completed : STATUS.failed, result.ok ? '执行完成' : '执行失败')
    if (!result.ok) emit('error', result.error || '任务失败')
  } catch (e) {
    const cur = getPlanningSession(sessionId)
    if (cur) {
      setSessionPhase(cur, STATUS.failed, '执行异常')
      log(cur, String(e.message || e))
    }
    emit('error', e.message || String(e))
  } finally {
    const cur = getPlanningSession(sessionId)
    if (cur) cur.busy = false
  }
}

watch(
  () => props.messages,
  () => {
    for (const s of sessions.value) {
      if (s.busy && s.runRequestId) applyProgressToSession(s)
    }
  },
  { deep: true },
)

function phaseBadgeClass(phase) {
  if (phase === STATUS.running || phase === STATUS.collecting || phase === STATUS.planning) {
    return 'bg-amber-500/20 text-amber-200'
  }
  if (phase === STATUS.completed || phase === STATUS.ready) return 'bg-emerald-500/20 text-emerald-200'
  if (phase === STATUS.failed) return 'bg-red-500/20 text-red-300'
  return 'bg-slate-500/20 text-slate-300'
}

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <div class="flex min-h-0 flex-1 overflow-hidden">
    <!-- 任务列表 -->
    <aside class="flex w-56 shrink-0 flex-col border-r border-edge bg-panel/40 md:w-64">
      <div class="flex items-center justify-between gap-2 border-b border-edge px-3 py-2">
        <p class="text-xs font-medium text-slate-400">任务列表</p>
        <button
          type="button"
          class="rounded bg-sky-600 px-2 py-0.5 text-xs text-white hover:bg-sky-500"
          @click="onNewTask"
        >
          新建
        </button>
      </div>
      <div class="min-h-0 flex-1 overflow-y-auto p-2">
        <button
          v-for="item in sessions"
          :key="item.id"
          type="button"
          class="mb-1 w-full rounded-lg border px-2 py-2 text-left transition"
          :class="
            item.id === session?.id
              ? 'border-sky-500/50 bg-sky-500/10'
              : 'border-transparent hover:border-edge hover:bg-white/5'
          "
          @click="onSelectTask(item.id)"
        >
          <div class="flex items-start justify-between gap-1">
            <p class="line-clamp-2 text-xs font-medium text-slate-200">{{ item.title }}</p>
            <button
              type="button"
              class="shrink-0 text-[10px] text-slate-500 hover:text-red-300"
              title="删除"
              @click="onRemoveTask(item.id, $event)"
            >
              ×
            </button>
          </div>
          <div class="mt-1 flex items-center justify-between gap-1">
            <span class="rounded px-1 py-0.5 text-[10px]" :class="phaseBadgeClass(item.phase)">
              {{ STATUS_LABEL[item.phase] || item.phase }}
            </span>
            <span class="text-[10px] text-slate-500">{{ formatTime(item.updatedAt) }}</span>
          </div>
          <p v-if="item.busy" class="mt-1 text-[10px] text-amber-300/90">进行中 · {{ item.statusText }}</p>
        </button>
        <p v-if="!sessions.length" class="px-1 py-4 text-center text-xs text-slate-500">暂无任务</p>
      </div>
    </aside>

    <!-- 详情 -->
    <div v-if="session" class="flex min-h-0 min-w-0 flex-1 flex-col gap-3 overflow-hidden p-3 md:p-4">
      <section class="shrink-0 rounded-xl border border-edge bg-panel/60 p-3">
        <p class="mb-2 text-xs font-medium text-slate-400">目标</p>
        <textarea
          v-model="session.goal"
          rows="3"
          class="w-full resize-y rounded-lg border border-edge bg-slate-950/60 px-3 py-2 text-sm text-slate-100 outline-none focus:border-sky-500/50"
          :disabled="session.busy"
          @change="touchSession(session)"
        />
        <div class="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg bg-sky-600 px-3 py-1.5 text-sm text-white hover:bg-sky-500 disabled:opacity-40"
            :disabled="session.busy"
            @click="onStart"
          >
            开始（质询→规划）
          </button>
          <button
            type="button"
            class="rounded-lg border border-edge px-3 py-1.5 text-sm text-slate-200 hover:bg-white/5 disabled:opacity-40"
            :disabled="!canRun"
            @click="onRun"
          >
            执行任务图
          </button>
          <button
            type="button"
            class="rounded-lg border border-edge px-3 py-1.5 text-sm text-slate-400 hover:bg-white/5 disabled:opacity-40"
            :disabled="session.busy"
            @click="onReset"
          >
            重置
          </button>
          <span class="self-center text-xs text-slate-500">{{ session.statusText }}</span>
        </div>
      </section>

      <section class="shrink-0 rounded-xl border border-edge bg-panel/60 p-3">
        <p class="mb-2 text-xs font-medium text-slate-400">质询</p>
        <p v-if="!currentQuestion" class="text-sm text-slate-500">（开始后在此回答问题）</p>
        <template v-else>
          <p class="text-sm text-slate-200">
            【{{ currentQuestion.id }}】{{ currentQuestion.prompt }}
          </p>
          <p v-if="currentQuestion.reason" class="mt-1 text-xs text-slate-500">
            （原因：{{ currentQuestion.reason }}）
          </p>
          <div class="mt-2 space-y-1">
            <label
              v-for="(c, i) in [...(currentQuestion.choices || []), OTHER_LABEL]"
              :key="i"
              class="flex cursor-pointer items-center gap-2 text-sm text-slate-300"
            >
              <input
                v-model="session.choice"
                type="radio"
                class="accent-sky-500"
                :value="c"
                :disabled="session.busy"
              />
              {{ i + 1 }}) {{ c }}
            </label>
          </div>
          <div v-if="session.choice === OTHER_LABEL" class="mt-2">
            <input
              v-model="session.otherText"
              type="text"
              placeholder="自行输入…"
              class="w-full rounded-lg border border-edge bg-slate-950/60 px-3 py-1.5 text-sm outline-none focus:border-sky-500/50"
              :disabled="session.busy"
            />
          </div>
          <button
            type="button"
            class="mt-2 rounded-lg bg-slate-700 px-3 py-1.5 text-sm text-white hover:bg-slate-600 disabled:opacity-40"
            :disabled="session.busy"
            @click="submitAnswer"
          >
            提交回答
          </button>
        </template>
      </section>

      <section class="shrink-0 rounded-xl border border-edge bg-panel/60 p-3">
        <p class="mb-2 text-xs font-medium text-slate-400">环境探测（只读，需批准后交执行→安全）</p>
        <p v-if="!session.envChecks.length" class="text-sm text-slate-500">（本轮无环境探测）</p>
        <template v-else>
          <p class="mb-2 text-xs text-slate-500">勾选允许执行的只读探测，未勾选视为拒绝：</p>
          <label
            v-for="(item, i) in session.envChecks"
            :key="i"
            class="flex cursor-pointer items-start gap-2 py-0.5 text-sm text-slate-300"
          >
            <input
              v-model="item.checked"
              type="checkbox"
              class="mt-1 accent-violet-500"
              :disabled="session.busy"
            />
            <span>
              [{{ item.q.id }}] {{ item.q.instruction }}
              <span v-if="item.q.purpose" class="text-slate-500">（{{ item.q.purpose }}）</span>
            </span>
          </label>
          <div class="mt-2 flex gap-2">
            <button
              type="button"
              class="rounded-lg border border-edge px-3 py-1.5 text-sm hover:bg-white/5 disabled:opacity-40"
              :disabled="session.busy"
              @click="toggleEnvAll"
            >
              全选/全不选
            </button>
            <button
              type="button"
              class="rounded-lg bg-violet-700 px-3 py-1.5 text-sm text-white hover:bg-violet-600 disabled:opacity-40"
              :disabled="session.busy"
              @click="approveEnv"
            >
              批准并执行探测
            </button>
          </div>
        </template>
      </section>

      <div class="grid min-h-0 flex-1 gap-3 lg:grid-cols-[minmax(0,3fr)_minmax(240px,2fr)]">
        <section class="flex min-h-0 flex-col rounded-xl border border-edge bg-panel/60 p-3">
          <div class="mb-2 flex gap-2 text-xs">
            <button
              type="button"
              class="rounded px-2 py-1"
              :class="session.tab === 'graph' ? 'bg-sky-600/30 text-sky-200' : 'text-slate-400 hover:bg-white/5'"
              @click="session.tab = 'graph'"
            >
              任务图
            </button>
            <button
              type="button"
              class="rounded px-2 py-1"
              :class="session.tab === 'json' ? 'bg-sky-600/30 text-sky-200' : 'text-slate-400 hover:bg-white/5'"
              @click="session.tab = 'json'"
            >
              JSON / 结果
            </button>
          </div>
          <div v-show="session.tab === 'graph'" class="min-h-0 flex-1">
            <TaskGraphCanvas
              :graph="session.graph"
              :initial-blocks="initialBlockLabels"
              :node-status="session.nodeStatus"
            />
          </div>
          <pre
            v-show="session.tab === 'json'"
            class="min-h-0 flex-1 overflow-auto rounded-lg bg-slate-950/80 p-3 font-mono text-xs text-slate-300"
          >{{ session.jsonText || '（暂无）' }}</pre>
        </section>

        <section class="flex min-h-0 flex-col rounded-xl border border-edge bg-panel/60 p-3">
          <p class="mb-2 text-xs font-medium text-slate-400">日志</p>
          <pre class="min-h-0 flex-1 overflow-auto font-mono text-xs leading-relaxed text-slate-300">{{
            session.logLines.join('\n') || '（开始后显示）'
          }}</pre>
        </section>
      </div>
    </div>

    <div v-else class="flex flex-1 items-center justify-center text-sm text-slate-500">
      点击「新建」开始一个规划任务
    </div>
  </div>
</template>
