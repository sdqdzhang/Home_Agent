<script setup>
import { computed, ref } from 'vue'
import { requestProcessor, UI_BLOCK_ID_PREFIX } from '../utils/processor.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
})

const emit = defineEmits(['error'])

const requirement = ref('根据上下文写出完整可运行的 Python 代码')
/** @type {import('vue').Ref<object[]>} */
const blocks = ref([])
const uiSeq = ref(0)

const busy = ref(false)
const errorText = ref('')
/** @type {import('vue').Ref<object|null>} */
const lastResult = ref(null)

const showDialog = ref(false)
const formType = ref('code')
const formProducer = ref('ui')
const formContent = ref("print('hello')")
const formMeta = ref('{\n  "language": "python"\n}')
const formError = ref('')

const selectedId = ref('')

const selectedBlock = computed(() => blocks.value.find((b) => b.id === selectedId.value) || null)

function nextUiId() {
  uiSeq.value += 1
  return `${UI_BLOCK_ID_PREFIX}${uiSeq.value}`
}

function preview(text, limit = 48) {
  const one = String(text || '').replace(/\n/g, ' ')
  return one.length > limit ? `${one.slice(0, limit)}…` : one
}

function openAddDialog() {
  formType.value = 'code'
  formProducer.value = 'ui'
  formContent.value = "print('hello')"
  formMeta.value = '{\n  "language": "python"\n}'
  formError.value = ''
  showDialog.value = true
}

function closeDialog() {
  showDialog.value = false
}

function confirmAdd() {
  formError.value = ''
  const type = formType.value.trim()
  const producer = formProducer.value.trim()
  const content = formContent.value
  if (!type) {
    formError.value = 'type 不能为空'
    return
  }
  if (!producer) {
    formError.value = 'producer 不能为空'
    return
  }
  if (!content.trim()) {
    formError.value = 'content 不能为空'
    return
  }

  let metadata = {}
  const metaRaw = formMeta.value.trim()
  if (metaRaw) {
    try {
      const parsed = JSON.parse(metaRaw)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        formError.value = 'metadata 必须是 JSON 对象'
        return
      }
      metadata = parsed
    } catch (e) {
      formError.value = `metadata JSON 无效: ${e.message}`
      return
    }
  }

  const id = nextUiId()
  blocks.value = [
    ...blocks.value,
    { id, type, content, producer, metadata },
  ]
  selectedId.value = id
  showDialog.value = false
}

function removeSelected() {
  if (!selectedId.value) return
  blocks.value = blocks.value.filter((b) => b.id !== selectedId.value)
  selectedId.value = blocks.value[0]?.id || ''
}

function clearBlocks() {
  blocks.value = []
  selectedId.value = ''
}

function loadSample() {
  requirement.value = '根据上下文把代码补全为一个完整的 hello 程序，并加一行注释说明用途'
  const id = nextUiId()
  blocks.value = [
    {
      id,
      type: 'code',
      content: "print('hello')",
      producer: 'ui',
      metadata: { language: 'python' },
    },
  ]
  selectedId.value = id
  lastResult.value = null
  errorText.value = ''
}

async function onProcess() {
  const req = requirement.value.trim()
  if (!req) {
    errorText.value = '请填写总要求'
    return
  }
  if (!blocks.value.length) {
    errorText.value = '请至少添加一个 DataBlock'
    return
  }

  busy.value = true
  errorText.value = ''
  lastResult.value = null

  try {
    const body = await requestProcessor(() => props.messages, props.agent.id, {
      requirement: req,
      blocks: blocks.value,
    })
    lastResult.value = body
    if (body?.ok === false) {
      errorText.value = body.error || '处理失败'
      emit('error', errorText.value)
    }
  } catch (e) {
    errorText.value = e.message || '处理失败'
    emit('error', errorText.value)
  } finally {
    busy.value = false
  }
}

loadSample()
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
    <div class="shrink-0 border-b border-surface-border bg-teal-500/5 px-4 py-2 md:px-5">
      <p class="text-xs font-medium text-teal-200">处理</p>
      <p class="mt-0.5 text-[11px] text-slate-500">
        总要求 + 一到多个 DataBlock → 模型产出一个 DataBlock（id 由系统分配）
      </p>
    </div>

    <div class="flex min-h-0 flex-1 flex-col md:flex-row">
      <!-- 输入 -->
      <section class="flex min-h-0 min-w-0 flex-1 flex-col border-b border-surface-border md:border-b-0 md:border-r">
        <div class="shrink-0 border-b border-surface-border px-4 py-2 md:px-5">
          <p class="text-xs font-medium text-slate-300">输入</p>
        </div>

        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3 scrollbar-thin md:px-5">
          <label class="block text-xs text-slate-500">总要求</label>
          <textarea
            v-model="requirement"
            rows="4"
            class="mt-1 w-full resize-y rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-teal-500/40"
            placeholder="例如：根据要求写出完整代码 / 总结文件内容"
          />

          <div class="mt-4 flex flex-wrap items-center gap-2">
            <p class="text-xs text-slate-500">上下文 DataBlock</p>
            <button
              type="button"
              class="rounded-md bg-teal-600/90 px-2.5 py-1 text-xs text-white hover:bg-teal-500"
              @click="openAddDialog"
            >
              添加…
            </button>
            <button
              type="button"
              class="rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 hover:bg-surface-raised"
              :disabled="!selectedId"
              @click="removeSelected"
            >
              删除选中
            </button>
            <button
              type="button"
              class="rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 hover:bg-surface-raised"
              @click="clearBlocks"
            >
              清空
            </button>
            <button
              type="button"
              class="rounded-md border border-surface-border px-2.5 py-1 text-xs text-slate-300 hover:bg-surface-raised"
              @click="loadSample"
            >
              示例
            </button>
          </div>

          <ul v-if="blocks.length" class="mt-2 space-y-1.5">
            <li
              v-for="b in blocks"
              :key="b.id"
              class="cursor-pointer rounded-lg border px-3 py-2 text-xs"
              :class="
                selectedId === b.id
                  ? 'border-teal-500/40 bg-teal-500/10'
                  : 'border-surface-border bg-surface-raised/40 hover:border-teal-500/20'
              "
              @click="selectedId = b.id"
            >
              <div class="flex flex-wrap gap-2 text-slate-400">
                <span class="font-mono text-teal-300">{{ b.id }}</span>
                <span>{{ b.type }}</span>
                <span>{{ b.producer }}</span>
              </div>
              <p class="mt-1 truncate text-slate-300">{{ preview(b.content) }}</p>
            </li>
          </ul>
          <p v-else class="mt-3 text-sm text-slate-500">尚未添加数据块</p>

          <div
            v-if="selectedBlock"
            class="mt-3 rounded-lg border border-surface-border bg-black/20 p-3"
          >
            <p class="text-[11px] text-slate-500">选中块详情</p>
            <pre class="mt-1 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-slate-300">{{
              JSON.stringify(selectedBlock, null, 2)
            }}</pre>
          </div>
        </div>

        <div class="shrink-0 border-t border-surface-border px-4 py-3 md:px-5">
          <button
            type="button"
            class="rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 disabled:opacity-50"
            :disabled="busy || loading"
            @click="onProcess"
          >
            {{ busy ? '处理中…' : '处理' }}
          </button>
          <p v-if="errorText" class="mt-2 text-xs text-red-300">{{ errorText }}</p>
        </div>
      </section>

      <!-- 输出 -->
      <section class="flex min-h-0 min-w-0 flex-1 flex-col">
        <div class="shrink-0 border-b border-surface-border px-4 py-2 md:px-5">
          <p class="text-xs font-medium text-slate-300">输出</p>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto px-4 py-3 scrollbar-thin md:px-5">
          <div v-if="busy" class="flex h-40 items-center justify-center text-sm text-slate-500">
            处理中，请稍候…
          </div>
          <div v-else-if="lastResult" class="space-y-3">
            <div
              class="rounded-xl border px-4 py-3"
              :class="
                lastResult.ok === false
                  ? 'border-red-500/30 bg-red-500/5'
                  : 'border-teal-500/30 bg-teal-500/5'
              "
            >
              <p class="text-xs font-medium text-teal-300">
                <template v-if="lastResult.ok && lastResult.output">
                  {{ lastResult.output.id }} · {{ lastResult.output.type }} ·
                  {{ lastResult.output.producer }}
                </template>
                <template v-else>失败</template>
              </p>
              <p v-if="lastResult.error" class="mt-2 text-sm text-red-300">{{ lastResult.error }}</p>
              <pre
                v-if="lastResult.output?.content != null"
                class="mt-2 max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg bg-black/25 px-3 py-2 font-mono text-xs text-slate-200"
              >{{ lastResult.output.content }}</pre>
              <details v-if="lastResult.output?.metadata" class="mt-2">
                <summary class="cursor-pointer text-xs text-slate-500">metadata</summary>
                <pre class="mt-1 whitespace-pre-wrap font-mono text-[11px] text-slate-400">{{
                  JSON.stringify(lastResult.output.metadata, null, 2)
                }}</pre>
              </details>
            </div>
            <details>
              <summary class="cursor-pointer text-xs text-slate-500">完整 JSON</summary>
              <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-slate-400">{{
                JSON.stringify(lastResult, null, 2)
              }}</pre>
            </details>
          </div>
          <p v-else class="py-10 text-center text-sm text-slate-500">结果将显示在这里</p>
        </div>
      </section>
    </div>

    <!-- 添加弹窗 -->
    <div
      v-if="showDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      @click.self="closeDialog"
    >
      <div class="w-full max-w-lg rounded-xl border border-surface-border bg-surface p-4 shadow-xl">
        <p class="text-sm font-medium text-slate-200">添加 DataBlock</p>
        <div class="mt-3 grid grid-cols-2 gap-3">
          <label class="block text-xs text-slate-500">
            type
            <input
              v-model="formType"
              class="mt-1 w-full rounded-md border border-surface-border bg-surface-raised px-2 py-1.5 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-teal-500/40"
            />
          </label>
          <label class="block text-xs text-slate-500">
            producer
            <input
              v-model="formProducer"
              class="mt-1 w-full rounded-md border border-surface-border bg-surface-raised px-2 py-1.5 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-teal-500/40"
            />
          </label>
        </div>
        <label class="mt-3 block text-xs text-slate-500">
          content
          <textarea
            v-model="formContent"
            rows="6"
            class="mt-1 w-full rounded-md border border-surface-border bg-surface-raised px-2 py-1.5 font-mono text-sm text-slate-200 outline-none focus:ring-1 focus:ring-teal-500/40"
          />
        </label>
        <label class="mt-3 block text-xs text-slate-500">
          metadata（JSON，可空）
          <textarea
            v-model="formMeta"
            rows="4"
            class="mt-1 w-full rounded-md border border-surface-border bg-surface-raised px-2 py-1.5 font-mono text-xs text-slate-200 outline-none focus:ring-1 focus:ring-teal-500/40"
          />
        </label>
        <p v-if="formError" class="mt-2 text-xs text-red-300">{{ formError }}</p>
        <div class="mt-4 flex justify-end gap-2">
          <button
            type="button"
            class="rounded-md border border-surface-border px-3 py-1.5 text-xs text-slate-300 hover:bg-surface-raised"
            @click="closeDialog"
          >
            取消
          </button>
          <button
            type="button"
            class="rounded-md bg-teal-600 px-3 py-1.5 text-xs text-white hover:bg-teal-500"
            @click="confirmAdd"
          >
            添加
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
