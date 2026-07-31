<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  /** @type {{ summary?: string, nodes?: object[] } | null} */
  graph: { type: Object, default: null },
  /** @type {{ id: string, label: string }[]} */
  initialBlocks: { type: Array, default: () => [] },
  /** @type {Record<string, { status: string, attempts?: number, error?: string }>} */
  nodeStatus: { type: Object, default: () => ({}) },
  /** 主对话内嵌时缩小高度 */
  compact: { type: Boolean, default: false },
})

defineEmits(['node-click'])

const GOAL_ID = 'goal'
const NODE_W = 200
const NODE_H = 96
const COL_GAP = 72
const ROW_GAP = 28
const MARGIN = 20

const canvasRef = ref(null)
const scale = ref(1)
const pan = ref({ x: 0, y: 0 })
const drag = ref(null)

/** 种类底色：执行=橙，处理=青绿，目标=蓝，环境=紫 */
const KIND_FILL = {
  goal: '#0c4a6e',
  env: '#4c1d95',
  process: '#134e4a',
  action: '#7c2d12',
}
const KIND_FILL_MUTED = {
  goal: '#082f49',
  env: '#2e1065',
  process: '#042f2e',
  action: '#431407',
}
const KIND_ACCENT = {
  goal: '#38bdf8',
  env: '#a78bfa',
  process: '#2dd4bf',
  action: '#fb923c',
}
const STATUS_STROKE = {
  pending: null,
  running: '#eab308',
  succeeded: '#22c55e',
  failed: '#ef4444',
  skipped: '#64748b',
}

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

const KIND_LEGEND = [
  { kind: 'action', label: '执行' },
  { kind: 'process', label: '处理' },
  { kind: 'goal', label: '目标' },
  { kind: 'env', label: '环境' },
]

function wrap(text, maxChars = 22, maxLines = 2) {
  const raw = String(text || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!raw) return ''
  const lines = []
  let i = 0
  while (i < raw.length && lines.length < maxLines) {
    let chunk = raw.slice(i, i + maxChars)
    i += maxChars
    if (i < raw.length && lines.length === maxLines - 1) {
      chunk = `${chunk.slice(0, -1)}…`
    }
    lines.push(chunk)
  }
  return lines.join('\n')
}

function nodeCaption(node) {
  if (!node) return ''
  const kind = node.kind || 'action'
  const outType = node.output?.type || '?'
  const body = kind === 'process' ? wrap(node.requirement) : wrap(node.instruction)
  return `${node.id} · ${outType}${body ? `\n${body}` : ''}`
}

function colorsFor(kind, status) {
  const k = KIND_ACCENT[kind] ? kind : 'action'
  let fill = KIND_FILL[k]
  if (status === 'pending' || status === 'skipped') fill = KIND_FILL_MUTED[k]
  if (status === 'failed') fill = '#450a0a'
  const stroke = STATUS_STROKE[status] || KIND_ACCENT[k]
  return { fill, stroke, accent: KIND_ACCENT[k] }
}

const layout = computed(() => {
  const graph = props.graph
  if (!graph?.nodes?.length) {
    return { nodes: [], edges: [], width: 400, height: 200 }
  }

  const preds = Object.fromEntries(graph.nodes.map((n) => [n.id, []]))
  const succ = { [GOAL_ID]: [] }
  const indeg = Object.fromEntries(graph.nodes.map((n) => [n.id, 0]))

  for (const n of graph.nodes) {
    const seen = new Set()
    for (const inp of n.inputs || []) {
      const src = inp.from || inp.from_node
      if (!src || seen.has(src)) continue
      seen.add(src)
      preds[n.id].push(src)
      if (!succ[src]) succ[src] = []
      succ[src].push(n.id)
      indeg[n.id] += 1
    }
  }

  const level = { [GOAL_ID]: 0 }
  const indegWork = { ...indeg }
  let queue = Object.keys(indeg).filter((id) => indeg[id] === 0)
  for (const nxt of succ[GOAL_ID] || []) {
    indegWork[nxt] -= 1
    if (indegWork[nxt] === 0) queue.push(nxt)
  }
  queue = [...new Set(queue)]
  const order = []
  while (queue.length) {
    const cur = queue.shift()
    order.push(cur)
    for (const nxt of succ[cur] || []) {
      indegWork[nxt] -= 1
      if (indegWork[nxt] === 0) queue.push(nxt)
    }
  }
  for (const nid of order) {
    const ps = preds[nid] || []
    level[nid] = ps.length
      ? 1 + Math.max(...ps.map((p) => level[p] ?? 0))
      : 1
  }
  for (const n of graph.nodes) {
    if (level[n.id] == null) level[n.id] = 1
  }

  const byLevel = { 0: [GOAL_ID] }
  const kinds = { [GOAL_ID]: 'goal' }
  const labels = { [GOAL_ID]: 'goal · 用户目标' }

  const referenced = new Set()
  for (const n of graph.nodes) {
    for (const inp of n.inputs || []) {
      const src = inp.from || inp.from_node
      if (src) referenced.add(src)
    }
  }
  for (const b of props.initialBlocks || []) {
    if (!referenced.has(b.id)) continue
    byLevel[0].push(b.id)
    kinds[b.id] = 'env'
    labels[b.id] = b.label || `${b.id} · 环境块`
    level[b.id] = 0
  }
  for (const n of graph.nodes) {
    const lv = level[n.id]
    if (!byLevel[lv]) byLevel[lv] = []
    byLevel[lv].push(n.id)
    kinds[n.id] = n.kind || 'action'
    labels[n.id] = nodeCaption(n)
  }

  const pos = {}
  let maxX = 0
  let maxY = 0
  for (const lv of Object.keys(byLevel).map(Number).sort((a, b) => a - b)) {
    const col = byLevel[lv]
    const x = MARGIN + lv * (NODE_W + COL_GAP)
    col.forEach((nid, row) => {
      const y = MARGIN + row * (NODE_H + ROW_GAP)
      pos[nid] = { x, y }
      maxX = Math.max(maxX, x + NODE_W)
      maxY = Math.max(maxY, y + NODE_H)
    })
  }

  const edges = []
  for (const n of graph.nodes) {
    const to = pos[n.id]
    if (!to) continue
    for (const inp of n.inputs || []) {
      const src = inp.from || inp.from_node
      const from = pos[src]
      if (!from) continue
      edges.push({
        key: `${src}->${n.id}:${inp.role}`,
        x1: from.x + NODE_W,
        y1: from.y + NODE_H / 2,
        x2: to.x,
        y2: to.y + NODE_H / 2,
        role: inp.role || '',
      })
    }
  }

  const nodes = Object.keys(pos).map((id) => {
    const kind = kinds[id] || 'action'
    const isInitial = kind === 'goal' || kind === 'env'
    const st = props.nodeStatus[id]
    const status = isInitial ? 'succeeded' : st?.status || 'pending'
    const attempts = st?.attempts || 0
    let caption = labels[id] || id
    if (!isInitial) {
      let tag = STATUS_LABEL[status] || status
      if ((status === 'running' || status === 'failed') && attempts > 0) tag = `${tag} #${attempts}`
      caption = `${caption}\n${tag}`
    }
    const { fill, stroke, accent } = colorsFor(kind, status)
    return {
      id,
      kind,
      kindLabel: KIND_LABEL[kind] || kind,
      status,
      x: pos[id].x,
      y: pos[id].y,
      caption,
      fill,
      stroke,
      accent,
    }
  })

  return {
    nodes,
    edges,
    width: maxX + MARGIN,
    height: maxY + MARGIN,
  }
})

function zoom(factor, clientX, clientY) {
  const el = canvasRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const mx = (clientX ?? rect.left + rect.width / 2) - rect.left
  const my = (clientY ?? rect.top + rect.height / 2) - rect.top
  const next = Math.min(2.5, Math.max(0.35, scale.value * factor))
  const applied = next / scale.value
  pan.value = {
    x: mx - (mx - pan.value.x) * applied,
    y: my - (my - pan.value.y) * applied,
  }
  scale.value = next
}

function resetView() {
  scale.value = 1
  pan.value = { x: 0, y: 0 }
}

function onWheel(e) {
  e.preventDefault()
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12
  zoom(factor, e.clientX, e.clientY)
}

function onPointerDown(e) {
  if (e.button !== 1 && e.button !== 2) return
  e.preventDefault()
  drag.value = { x: e.clientX, y: e.clientY, panX: pan.value.x, panY: pan.value.y }
  e.currentTarget.setPointerCapture?.(e.pointerId)
}

function onPointerMove(e) {
  if (!drag.value) return
  pan.value = {
    x: drag.value.panX + (e.clientX - drag.value.x),
    y: drag.value.panY + (e.clientY - drag.value.y),
  }
}

function onPointerUp() {
  drag.value = null
}

watch(
  () => props.graph,
  async () => {
    await nextTick()
    resetView()
  },
)

onMounted(resetView)
</script>

<template>
  <div class="flex h-full flex-col" :class="compact ? 'min-h-[220px]' : 'min-h-[280px]'">
    <div v-if="!compact" class="mb-2 flex flex-wrap items-center gap-2 text-xs text-slate-400">
      <button
        type="button"
        class="rounded border border-edge px-2 py-0.5 hover:bg-white/5"
        @click="zoom(1.15)"
      >
        ＋
      </button>
      <button
        type="button"
        class="rounded border border-edge px-2 py-0.5 hover:bg-white/5"
        @click="zoom(1 / 1.15)"
      >
        －
      </button>
      <button
        type="button"
        class="rounded border border-edge px-2 py-0.5 hover:bg-white/5"
        @click="resetView"
      >
        重置
      </button>
      <span>{{ Math.round(scale * 100) }}%</span>
      <span class="text-slate-500">滚轮缩放 · 中键/右键拖动</span>
      <span class="mx-1 text-slate-600">|</span>
      <span
        v-for="item in KIND_LEGEND"
        :key="item.kind"
        class="inline-flex items-center gap-1"
      >
        <span
          class="inline-block h-2.5 w-2.5 rounded-sm"
          :style="{ background: KIND_ACCENT[item.kind] }"
        />
        {{ item.label }}
      </span>
    </div>
    <div
      v-else
      class="mb-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-500"
    >
      <button type="button" class="rounded border border-edge px-1.5 py-0.5 hover:bg-white/5" @click="zoom(1.15)">＋</button>
      <button type="button" class="rounded border border-edge px-1.5 py-0.5 hover:bg-white/5" @click="zoom(1 / 1.15)">－</button>
      <span
        v-for="item in KIND_LEGEND"
        :key="item.kind"
        class="inline-flex items-center gap-0.5"
      >
        <span
          class="inline-block h-2 w-2 rounded-sm"
          :style="{ background: KIND_ACCENT[item.kind] }"
        />
        {{ item.label }}
      </span>
    </div>
    <div
      ref="canvasRef"
      class="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-edge bg-slate-950"
      @wheel="onWheel"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @contextmenu.prevent
    >
      <svg
        class="h-full w-full"
        :viewBox="`0 0 ${Math.max(layout.width, 400)} ${Math.max(layout.height, 240)}`"
        preserveAspectRatio="xMinYMin meet"
      >
        <g :transform="`translate(${pan.x}, ${pan.y}) scale(${scale})`">
          <path
            v-for="e in layout.edges"
            :key="e.key"
            :d="`M ${e.x1} ${e.y1} C ${e.x1 + COL_GAP / 2} ${e.y1}, ${e.x2 - COL_GAP / 2} ${e.y2}, ${e.x2} ${e.y2}`"
            fill="none"
            stroke="#64748b"
            stroke-width="1.5"
            marker-end="url(#arrow)"
          />
          <text
            v-for="e in layout.edges"
            :key="`${e.key}-role`"
            :x="(e.x1 + e.x2) / 2"
            :y="(e.y1 + e.y2) / 2 - 6"
            fill="#94a3b8"
            font-size="10"
            text-anchor="middle"
          >
            {{ e.role }}
          </text>
          <g
            v-for="n in layout.nodes"
            :key="n.id"
            class="cursor-pointer"
            @click.stop="$emit('node-click', n.id)"
          >
            <rect
              :x="n.x"
              :y="n.y"
              :width="NODE_W"
              :height="NODE_H"
              rx="8"
              :fill="n.fill"
              :stroke="n.stroke"
              :stroke-width="n.status === 'running' ? 3 : 2"
            />
            <rect
              :x="n.x + 2"
              :y="n.y + 10"
              width="4"
              :height="NODE_H - 20"
              rx="2"
              :fill="n.accent"
            />
            <text
              :x="n.x + 12"
              :y="n.y + 16"
              :fill="n.accent"
              font-size="10"
              font-weight="700"
            >
              {{ n.kindLabel }}
            </text>
            <text
              :x="n.x + NODE_W / 2 + 2"
              :y="n.y + NODE_H / 2 + 8"
              fill="#e2e8f0"
              font-size="11"
              text-anchor="middle"
              dominant-baseline="middle"
            >
              <tspan
                v-for="(line, i) in n.caption.split('\n')"
                :key="i"
                :x="n.x + NODE_W / 2 + 2"
                :dy="i === 0 ? -(n.caption.split('\n').length - 1) * 6.5 : 13"
              >
                {{ line }}
              </tspan>
            </text>
          </g>
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 Z" fill="#64748b" />
            </marker>
          </defs>
        </g>
      </svg>
      <p
        v-if="!graph?.nodes?.length"
        class="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-slate-500"
      >
        任务图将显示在这里
      </p>
    </div>
  </div>
</template>
