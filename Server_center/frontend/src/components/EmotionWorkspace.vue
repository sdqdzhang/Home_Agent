<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import {
  latestMindSnapshot,
  personaSummaryLines,
  requestEmotionAction,
} from '../utils/emotion.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
  live: { type: Boolean, default: false },
})

const emit = defineEmits(['error'])

const busy = ref(false)
const statusText = ref('')
const errorText = ref('')
const pickId = ref('')

/** 优先用带 request 的最新快照；否则频道内最新 mind_snapshot */
const snapshot = computed(() => latestMindSnapshot(props.messages, props.agent))

const persona = computed(() => snapshot.value?.persona || null)
const mindState = computed(() => snapshot.value?.mind_state || null)
const mindContext = computed(() => String(snapshot.value?.mind_context || '').trim())
const available = computed(() =>
  Array.isArray(snapshot.value?.available_personas) ? snapshot.value.available_personas : [],
)
const recentChanges = computed(() =>
  Array.isArray(snapshot.value?.recent_changes) ? snapshot.value.recent_changes : [],
)
const activeSpec = computed(
  () => snapshot.value?.active_spec || snapshot.value?.persona_spec || persona.value?.id || '',
)
const enabled = computed(() => snapshot.value?.enabled === true)

const summaryLines = computed(() => personaSummaryLines(persona.value))
const valuePriorities = computed(() => {
  const values = persona.value?.values
  if (Array.isArray(values)) return values
  return Array.isArray(values?.priorities) ? values.priorities : []
})
const valueConflicts = computed(() => {
  const values = persona.value?.values
  return Array.isArray(values?.conflicts) ? values.conflicts : []
})
const worldviewSections = computed(() => Object.entries(persona.value?.worldview || {}))
const tendencyGroups = computed(() => Object.entries(persona.value?.tendencies || {}))
const legacyPolicyNotes = computed(() =>
  Array.isArray(persona.value?.extra?.legacy_policy_notes) ? persona.value.extra.legacy_policy_notes : [],
)
const resolverDebug = computed(() =>
  Array.isArray(snapshot.value?.resolver_debug) ? snapshot.value.resolver_debug : [],
)

const emotion = computed(() => mindState.value?.emotion || null)
const relationship = computed(() => mindState.value?.relationship || null)
const display = computed(() => snapshot.value?.display || {})
const showDebugNumbers = ref(false)
const recentEvents = computed(() =>
  Array.isArray(mindState.value?.recent_events) ? mindState.value.recent_events : [],
)

function loadValue(emo) {
  if (!emo) return 0
  if (typeof emo.cognitive_load === 'number') return emo.cognitive_load
  if (typeof emo.energy === 'number') return emo.energy
  return 0
}

watch(
  available,
  (list) => {
    if (!list.length) return
    const active = activeSpec.value
    if (active && list.some((p) => p.id === active)) {
      pickId.value = active
    } else if (!pickId.value) {
      pickId.value = list[0].id
    }
  },
  { immediate: true },
)

function getMessages() {
  return props.messages
}

function pct(v) {
  if (typeof v !== 'number' || Number.isNaN(v)) return 0
  return Math.max(0, Math.min(100, Math.round(v * 100)))
}

function preview(text, limit = 140) {
  const one = String(text || '').replace(/\n/g, ' ').trim()
  if (!one) return '—'
  return one.length > limit ? `${one.slice(0, limit)}…` : one
}

function unitText(unit) {
  if (typeof unit === 'string') return unit
  return String(unit?.text || unit?.summary || '').trim()
}

function unitMeta(unit) {
  if (!unit || typeof unit !== 'object') return ''
  const bits = []
  if (unit.visibility) bits.push(unit.visibility)
  if (typeof unit.weight === 'number') bits.push(`w=${unit.weight.toFixed(2)}`)
  if (typeof unit.strength === 'number') bits.push(`s=${unit.strength.toFixed(2)}`)
  if (Array.isArray(unit.tags) && unit.tags.length) bits.push(unit.tags.join(','))
  return bits.join(' · ')
}

async function run(action, extra = {}) {
  busy.value = true
  errorText.value = ''
  try {
    await requestEmotionAction(getMessages, { action, ...extra })
    statusText.value = `已同步 · ${new Date().toLocaleTimeString('zh-CN')}`
  } catch (e) {
    errorText.value = e?.message || String(e)
    emit('error', errorText.value)
  } finally {
    busy.value = false
  }
}

async function refresh() {
  await run('refresh')
}

async function applyPersona() {
  const id = String(pickId.value || '').trim()
  if (!id) return
  await run('set_persona', { persona: id })
}

async function reloadCurrent() {
  await run('reload_persona')
}

async function toggleEnabled() {
  await run('set_enabled', { enabled: !enabled.value })
}

onMounted(() => {
  refresh().catch(() => {})
})
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-auto px-4 py-4 text-sm text-zinc-200">
    <!-- 总开关 -->
    <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-sm font-medium text-zinc-100">心智与状态模块</h2>
          <p class="mt-0.5 text-xs text-zinc-500">
            关闭时主对话不注入人格/情绪，行为与接入前一致（适合工作任务）。开启后才会使用人格与动态状态。
          </p>
        </div>
        <button
          type="button"
          role="switch"
          :aria-checked="enabled"
          class="relative h-7 w-12 shrink-0 rounded-full transition-colors disabled:opacity-50"
          :class="enabled ? 'bg-teal-600' : 'bg-zinc-700'"
          :disabled="busy"
          @click="toggleEnabled"
        >
          <span
            class="absolute top-0.5 left-0.5 h-6 w-6 rounded-full bg-white transition-transform"
            :class="enabled ? 'translate-x-5' : 'translate-x-0'"
          />
        </button>
      </div>
      <p class="mt-2 font-mono text-[11px]" :class="enabled ? 'text-teal-400/90' : 'text-zinc-500'">
        当前：{{ enabled ? '已开启 · 主对话注入 Mind Context' : '已关闭 · 主对话不受影响' }}
      </p>
    </section>

    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <p class="text-xs text-zinc-500">
        人格文件即插即用：可先配置人格，再开启模块生效。
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          :disabled="busy"
          @click="refresh"
        >
          刷新
        </button>
        <button
          type="button"
          class="rounded border border-zinc-700 px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 disabled:opacity-50"
          :disabled="busy"
          @click="reloadCurrent"
        >
          重载文件
        </button>
      </div>
    </div>

    <p v-if="errorText" class="mb-3 rounded border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
      {{ errorText }}
    </p>
    <p v-if="statusText" class="mb-2 text-[11px] text-zinc-500">{{ statusText }}</p>
    <p v-if="(loading || busy) && !snapshot" class="text-zinc-500">加载中…</p>
    <p v-else-if="!snapshot" class="text-zinc-500">
      尚无 mind_snapshot。点击刷新，或确认 Local Agent 已启动。
    </p>

    <template v-else>
      <!-- 人格切换 -->
      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">人格即插即用</h2>
        <div class="flex flex-wrap items-end gap-2">
          <label class="flex min-w-[12rem] flex-1 flex-col gap-1 text-xs text-zinc-500">
            可用人格（personas/*.yaml）
            <select
              v-model="pickId"
              class="rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-sm text-zinc-200"
              :disabled="busy || !available.length"
            >
              <option v-for="p in available" :key="p.id" :value="p.id">
                {{ p.id }}
              </option>
            </select>
          </label>
          <button
            type="button"
            class="rounded bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-900 hover:bg-white disabled:opacity-50"
            :disabled="busy || !pickId || pickId === activeSpec"
            @click="applyPersona"
          >
            切换并载入
          </button>
        </div>
        <p class="mt-2 text-[11px] text-zinc-500">
          当前激活：
          <span class="font-mono text-zinc-300">{{ activeSpec || '—' }}</span>
          <span v-if="persona?.display_name"> · {{ persona.display_name }}</span>
          <span v-if="persona?.source_path" class="ml-1 break-all text-zinc-600">
            （{{ persona.source_path }}）
          </span>
        </p>
      </section>

      <p
        v-if="!enabled"
        class="mb-3 rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-xs text-amber-200/80"
      >
        模块已关闭：下方可预览与切换人格，但不会注入主对话，也不会做情绪更新。
      </p>

      <div :class="enabled ? '' : 'opacity-70'">
      <!-- 整理后的人格档案 -->
      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          载入人格（整理视图）
        </h2>
        <template v-if="persona">
          <div class="mb-3 flex flex-wrap items-baseline gap-2">
            <span class="text-base font-medium text-zinc-100">{{ persona.display_name || persona.id }}</span>
            <span class="font-mono text-[11px] text-zinc-500">id={{ persona.id }}</span>
            <span v-if="persona.version" class="text-[11px] text-zinc-600">v{{ persona.version }}</span>
            <span
              v-if="persona.ui?.personality"
              class="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300"
            >{{ persona.ui.personality }}</span>
          </div>

          <div class="mb-3">
            <p class="mb-1 text-[11px] uppercase tracking-wide text-zinc-500">人格摘要（整理视图，不等于每轮注入）</p>
            <div class="space-y-1 rounded bg-zinc-950/70 px-3 py-2 text-xs leading-relaxed text-zinc-300">
              <p v-for="(line, i) in summaryLines" :key="i">{{ line }}</p>
              <p v-if="!summaryLines.length" class="text-zinc-600">—</p>
            </div>
          </div>

          <p
            v-if="persona && persona.structured_from_file === false"
            class="mb-3 rounded border border-zinc-700/60 bg-zinc-950/50 px-2 py-1.5 text-[11px] text-zinc-500"
          >
            此人格文件主要靠上方「摘要」定义（未写 V1 结构化段）。
            下面若出现 HomeAgent / 清晰直接 等，是系统占位默认值，不是文件正文。
          </p>

          <template v-if="persona?.structured_from_file !== false">
          <dl class="mb-3 grid grid-cols-1 gap-2 text-xs md:grid-cols-3">
            <div>
              <dt class="text-zinc-500">名称</dt>
              <dd>{{ persona.identity?.name || '—' }}</dd>
            </div>
            <div>
              <dt class="text-zinc-500">角色</dt>
              <dd>{{ persona.identity?.role || '—' }}</dd>
            </div>
            <div>
              <dt class="text-zinc-500">自称</dt>
              <dd>{{ persona.identity?.self_reference || '—' }}</dd>
            </div>
          </dl>

          <div class="mb-3 grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <p class="mb-1 text-[11px] text-zinc-500">价值倾向</p>
              <ul class="space-y-1 text-xs text-zinc-300">
                <li v-for="(v, i) in valuePriorities" :key="i">
                  {{ unitText(v) }}
                  <span v-if="unitMeta(v)" class="ml-1 font-mono text-[10px] text-zinc-600">
                    {{ unitMeta(v) }}
                  </span>
                </li>
                <li v-if="!valuePriorities.length" class="text-zinc-600">—</li>
              </ul>
            </div>
            <div>
              <p class="mb-1 text-[11px] text-zinc-500">UI 特质</p>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="(t, i) in (persona.ui?.traits || [])"
                  :key="i"
                  class="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300"
                >{{ t }}</span>
                <span v-if="!(persona.ui?.traits || []).length" class="text-xs text-zinc-600">—</span>
              </div>
            </div>
          </div>

          <div v-if="valueConflicts.length" class="mb-3">
            <p class="mb-1 text-[11px] text-zinc-500">价值冲突倾向</p>
            <ul class="list-inside list-disc space-y-0.5 text-xs text-zinc-300">
              <li v-for="(v, i) in valueConflicts" :key="i">
                {{ unitText(v) }}
                <span v-if="unitMeta(v)" class="ml-1 font-mono text-[10px] text-zinc-600">
                  {{ unitMeta(v) }}
                </span>
              </li>
            </ul>
          </div>

          <div v-if="worldviewSections.length" class="mb-3">
            <p class="mb-1 text-[11px] text-zinc-500">世界观 / beliefs</p>
            <div class="space-y-2 text-xs text-zinc-300">
              <div v-for="([name, section]) in worldviewSections" :key="name" class="rounded bg-zinc-950/50 px-2 py-1.5">
                <p class="mb-1 font-mono text-[11px] text-zinc-500">{{ name }}</p>
                <p v-if="section?.summary" class="mb-1">{{ section.summary }}</p>
                <ul class="list-inside list-disc space-y-0.5">
                  <li v-for="(b, i) in (section?.beliefs || [])" :key="i">
                    {{ unitText(b) }}
                    <span v-if="unitMeta(b)" class="ml-1 font-mono text-[10px] text-zinc-600">
                      {{ unitMeta(b) }}
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <div v-if="tendencyGroups.length" class="mb-3">
            <p class="mb-1 text-[11px] text-zinc-500">行为倾向（tendencies，不是硬规则）</p>
            <div class="space-y-2 text-xs text-zinc-300">
              <div v-for="([group, items]) in tendencyGroups" :key="group" class="rounded bg-zinc-950/50 px-2 py-1.5">
                <p class="mb-1 font-mono text-[11px] text-zinc-500">{{ group }}</p>
                <ul class="list-inside list-disc space-y-0.5">
                  <li v-for="(t, i) in items" :key="i">
                    {{ unitText(t) }}
                    <span v-if="unitMeta(t)" class="ml-1 font-mono text-[10px] text-zinc-600">
                      {{ unitMeta(t) }}
                    </span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          <div class="mb-3">
            <p class="mb-1 text-[11px] text-zinc-500">交流风格</p>
            <dl class="grid grid-cols-2 gap-2 text-xs md:grid-cols-5">
              <div>
                <dt class="text-zinc-600">语气</dt>
                <dd>{{ persona.style?.tone || '—' }}</dd>
              </div>
              <div>
                <dt class="text-zinc-600">语言</dt>
                <dd>{{ persona.style?.language || '—' }}</dd>
              </div>
              <div>
                <dt class="text-zinc-600">幽默</dt>
                <dd>{{ persona.style?.humor || '—' }}</dd>
              </div>
              <div>
                <dt class="text-zinc-600">正式度</dt>
                <dd>{{ persona.style?.formality || '—' }}</dd>
              </div>
              <div>
                <dt class="text-zinc-600">emoji</dt>
                <dd>{{ persona.style?.emoji ? '允许' : '禁止' }}</dd>
              </div>
            </dl>
          </div>

          <div>
            <p class="mb-1 text-[11px] text-zinc-500">Policy 备注（旧字段仅调试，不进入 Persona Core）</p>
            <ul class="list-inside list-disc space-y-0.5 text-xs text-zinc-400">
              <li v-for="(p, i) in legacyPolicyNotes" :key="i">{{ p }}</li>
              <li v-if="!legacyPolicyNotes.length" class="list-none text-zinc-600">—</li>
            </ul>
          </div>
          </template>

          <div v-else class="mb-1">
            <p class="mb-1 text-[11px] text-zinc-500">UI 标签（来自文件 ui 段）</p>
            <div class="flex flex-wrap gap-1">
              <span
                v-if="persona.ui?.personality"
                class="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300"
              >{{ persona.ui.personality }}</span>
              <span
                v-for="(t, i) in (persona.ui?.traits || [])"
                :key="i"
                class="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300"
              >{{ t }}</span>
            </div>
          </div>
        </template>
        <p v-else class="text-xs text-zinc-500">无人格数据</p>
      </section>

      <!-- 动态状态 -->
      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">当前动态状态</h2>
        <div v-if="emotion" class="mb-3 flex flex-wrap items-center gap-2">
          <span class="text-lg text-zinc-100">{{ emotion.mood }}</span>
          <span class="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-300">
            {{ display.interaction_mode || mindState?.interaction_mode || '—' }}
          </span>
          <span class="rounded bg-zinc-800 px-2 py-0.5 text-[11px] text-zinc-400">
            {{ display.collaboration || display.work_mode || mindState?.work_mode || '—' }}
          </span>
          <span
            v-if="emotion.persistence && emotion.persistence !== 'none'"
            class="rounded bg-zinc-800/80 px-2 py-0.5 text-[11px] text-zinc-500"
          >惯性 {{ emotion.persistence }}</span>
        </div>

        <dl class="grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
          <div>
            <dt class="text-zinc-500">情绪强度</dt>
            <dd>{{ display.intensity || '—' }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">认知负荷</dt>
            <dd>{{ display.cognitive_load || '—' }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">专注</dt>
            <dd>{{ display.focus || '—' }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">关系</dt>
            <dd>{{ display.familiarity || '—' }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">当前亲近</dt>
            <dd>{{ display.warmth || '—' }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">互动模式</dt>
            <dd>{{ display.interaction_mode || mindState?.interaction_mode || '—' }}</dd>
          </div>
        </dl>

        <dl v-if="relationship" class="mt-3 grid grid-cols-2 gap-2 text-xs md:grid-cols-3">
          <div>
            <dt class="text-zinc-500">氛围</dt>
            <dd>{{ relationship.vibe || display.vibe || '—' }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">有意义互动</dt>
            <dd class="font-mono">{{ relationship.meaningful_turns ?? 0 }}</dd>
          </div>
          <div>
            <dt class="text-zinc-500">总轮次（统计）</dt>
            <dd class="font-mono">{{ relationship.turn_count ?? '—' }}</dd>
          </div>
        </dl>

        <p v-if="emotion?.unresolved_affect" class="mt-3 text-xs text-amber-200/80">
          未化解线索：{{ emotion.unresolved_affect }}
        </p>

        <div v-if="(mindState?.behavior_hints || []).length" class="mt-3">
          <p class="mb-1 text-[11px] text-zinc-500">当前行为倾向</p>
          <ul class="list-inside list-disc space-y-0.5 text-xs text-zinc-300">
            <li v-for="(h, i) in mindState.behavior_hints" :key="i">{{ h }}</li>
          </ul>
        </div>

        <div v-if="recentEvents.length" class="mt-3">
          <p class="mb-1 text-[11px] text-zinc-500">近期事件</p>
          <ul class="max-h-28 space-y-0.5 overflow-auto font-mono text-[11px] text-zinc-500">
            <li v-for="(ev, i) in recentEvents.slice().reverse()" :key="i">
              {{ ev.type }} · {{ ev.significance }} · {{ preview(ev.summary, 60) }}
            </li>
          </ul>
        </div>

        <button
          type="button"
          class="mt-3 text-[11px] text-zinc-500 hover:text-zinc-400"
          @click="showDebugNumbers = !showDebugNumbers"
        >
          {{ showDebugNumbers ? '收起' : '展开' }}内部数值（调试）
        </button>
        <div v-if="showDebugNumbers && emotion" class="mt-2 space-y-2">
          <div
            v-for="row in [
              { label: 'intensity', value: emotion.intensity },
              { label: 'cognitive_load', value: loadValue(emotion) },
              { label: 'focus', value: emotion.focus },
              { label: 'familiarity', value: relationship?.familiarity },
              { label: 'current_warmth', value: relationship?.current_warmth },
            ]"
            :key="row.label"
          >
            <div class="mb-0.5 flex justify-between text-[11px] text-zinc-500">
              <span>{{ row.label }}</span>
              <span class="font-mono">{{ pct(row.value) }}%</span>
            </div>
            <div class="h-1.5 overflow-hidden rounded bg-zinc-800">
              <div class="h-full rounded bg-teal-600/80" :style="{ width: `${pct(row.value)}%` }" />
            </div>
          </div>
        </div>
      </section>

      <!-- Mind Context -->
      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          Mind Context（主模型所见）
        </h2>
        <pre
          class="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded bg-zinc-950/70 px-3 py-2 font-mono text-[11px] leading-relaxed text-zinc-400"
        >{{ mindContext || '—' }}</pre>
      </section>

      <section v-if="resolverDebug.length" class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">
          Resolver Debug（未注入主模型）
        </h2>
        <ul class="max-h-40 space-y-1 overflow-auto text-xs text-zinc-400">
          <li v-for="(row, i) in resolverDebug" :key="i" class="rounded bg-zinc-950/50 px-2 py-1">
            <div class="mb-0.5 flex flex-wrap items-center gap-2 font-mono text-[11px] text-zinc-500">
              <span>{{ row.source || 'unknown' }}</span>
              <span>score={{ row.score ?? '—' }}</span>
              <span>{{ row.visibility || '—' }}</span>
              <span v-if="(row.tags || []).length">{{ row.tags.join(',') }}</span>
            </div>
            <p>{{ row.preview || row.reason || '—' }}</p>
            <p v-if="row.reason" class="mt-0.5 font-mono text-[10px] text-zinc-600">{{ row.reason }}</p>
          </li>
        </ul>
      </section>

      <!-- 变更记录 -->
      <section class="mb-4 rounded border border-zinc-800 bg-zinc-900/40 p-3">
        <h2 class="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-400">近期状态变更</h2>
        <ul v-if="recentChanges.length" class="max-h-40 space-y-1 overflow-auto text-xs text-zinc-400">
          <li v-for="(c, i) in recentChanges.slice().reverse()" :key="i" class="font-mono text-[11px]">
            #{{ c.turn_index }} · {{ c.source }} · {{ preview(c.summary || c.reason) }}
          </li>
        </ul>
        <p v-else class="text-xs text-zinc-500">暂无</p>
      </section>
      </div>
    </template>
  </div>
</template>
