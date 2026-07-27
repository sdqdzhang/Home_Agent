import { computed, reactive, ref } from 'vue'

/**
 * 规划任务会话（模块级，切换 Agent 不会丢）
 * @typedef {object} PlanningSession
 */

export const STATUS = {
  idle: 'idle',
  collecting: 'collecting',
  planning: 'planning',
  ready: 'ready',
  running: 'running',
  completed: 'completed',
  failed: 'failed',
}

export const STATUS_LABEL = {
  idle: '草稿',
  collecting: '信息收集中',
  planning: '出图中',
  ready: '可执行',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
}

/** @type {import('vue').Ref<PlanningSession[]>} */
export const planningSessions = ref([])

/** @type {import('vue').Ref<string|null>} */
export const activePlanningId = ref(null)

export const activePlanningSession = computed(
  () => planningSessions.value.find((s) => s.id === activePlanningId.value) || null,
)

function now() {
  return Date.now()
}

function previewGoal(goal, limit = 36) {
  const one = String(goal || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!one) return '（未命名任务）'
  return one.length > limit ? `${one.slice(0, limit)}…` : one
}

/** @returns {PlanningSession} */
export function createEmptySession(goal = '') {
  const id = crypto.randomUUID()
  return reactive({
    id,
    goal:
      goal ||
      '在工作区创建一个 demo_hello 目录，生成一个打印 Hello 的 Python 脚本并写入 demo_hello/main.py',
    title: previewGoal(goal),
    createdAt: now(),
    updatedAt: now(),
    phase: STATUS.idle,
    statusText: '就绪',
    busy: false,
    logLines: [],
    tab: 'graph',
    history: [],
    envRecords: [],
    envBlocks: [],
    roundIndex: 1,
    envSeq: 0,
    pendingQuestions: [],
    pendingEnv: [],
    questionsDone: true,
    envDone: true,
    envChecks: [],
    choice: '',
    otherText: '',
    graph: null,
    nodeStatus: {},
    jsonText: '',
    runRequestId: '',
  })
}

export function touchSession(session) {
  if (!session) return
  session.updatedAt = now()
  session.title = previewGoal(session.goal)
}

export function addPlanningSession(goal = '') {
  const session = createEmptySession(goal)
  planningSessions.value = [session, ...planningSessions.value]
  activePlanningId.value = session.id
  return session
}

export function selectPlanningSession(id) {
  if (!planningSessions.value.some((s) => s.id === id)) return null
  activePlanningId.value = id
  return planningSessions.value.find((s) => s.id === id) || null
}

export function removePlanningSession(id) {
  const target = planningSessions.value.find((s) => s.id === id)
  if (target?.busy) return false
  planningSessions.value = planningSessions.value.filter((s) => s.id !== id)
  if (activePlanningId.value === id) {
    activePlanningId.value = planningSessions.value[0]?.id || null
  }
  return true
}

export function getPlanningSession(id) {
  return planningSessions.value.find((s) => s.id === id) || null
}

export function ensureActivePlanningSession() {
  if (activePlanningSession.value) return activePlanningSession.value
  return addPlanningSession()
}

export function setSessionPhase(session, phase, statusText) {
  if (!session) return
  session.phase = phase
  if (statusText != null) session.statusText = statusText
  touchSession(session)
}

export function appendSessionLog(session, msg) {
  if (!session) return
  session.logLines = [...session.logLines, msg]
  touchSession(session)
}

export function resetSessionCollection(session, { keepGoal = true } = {}) {
  if (!session) return
  const goal = keepGoal ? session.goal : ''
  Object.assign(session, {
    goal: keepGoal ? session.goal : createEmptySession().goal,
    phase: STATUS.idle,
    statusText: '已重置',
    busy: false,
    logLines: [],
    tab: 'graph',
    history: [],
    envRecords: [],
    envBlocks: [],
    roundIndex: 1,
    envSeq: 0,
    pendingQuestions: [],
    pendingEnv: [],
    questionsDone: true,
    envDone: true,
    envChecks: [],
    choice: '',
    otherText: '',
    graph: null,
    nodeStatus: {},
    jsonText: '',
    runRequestId: '',
  })
  if (!keepGoal) session.goal = goal || createEmptySession().goal
  touchSession(session)
}

export function sortedPlanningSessions() {
  return [...planningSessions.value].sort((a, b) => b.updatedAt - a.updatedAt)
}
