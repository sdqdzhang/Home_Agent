<script setup>
import { computed, onMounted, ref } from 'vue'
import { llmConfigErrorText, requestLlmConfig } from '../utils/llmConfig.js'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  agent: { type: Object, required: true },
  live: { type: Boolean, default: false },
})

const emit = defineEmits(['responded', 'error'])

const busy = ref(false)
const statusText = ref('')
const errorText = ref('')

const endpoints = ref([])
const bindings = ref([])
const slots = ref([])
const resolved = ref({})

const selectedEndpointId = ref('')
const isNewEndpoint = ref(false)
const form = ref(emptyForm())

const bindSlot = ref('')
const bindEndpointId = ref('')
const bindModelOverride = ref('')

function emptyForm() {
  return {
    id: '',
    name: '',
    capability: 'chat',
    base_url: 'http://127.0.0.1:11434/v1',
    api_key: 'ollama',
    default_model: 'llama3.2',
    timeout: '120',
    max_tokens: '4096',
    temperature: '0.2',
    enabled: true,
  }
}

const selectedEndpoint = computed(() =>
  endpoints.value.find((ep) => ep.id === selectedEndpointId.value) || null,
)

const endpointOptions = computed(() =>
  endpoints.value.map((ep) => ({
    id: ep.id,
    label: `${ep.name} (${ep.id})`,
    capability: ep.capability,
  })),
)

const bindingRows = computed(() => {
  const epMap = Object.fromEntries(endpoints.value.map((ep) => [ep.id, ep.name]))
  return slots.value.map((slot) => {
    const binding = bindings.value.find((b) => b.slot_key === slot.slot_key)
    const res = resolved.value[slot.slot_key] || {}
    return {
      slot_key: slot.slot_key,
      label: slot.label,
      endpoint_id: binding?.endpoint_id || '',
      endpoint_name: binding ? epMap[binding.endpoint_id] || binding.endpoint_id : '—',
      model_override: binding?.model_override || '',
      resolved_model: res.model || '—',
      source: res.source || '—',
    }
  })
})

function getMessages() {
  return props.messages
}

function applySnapshot(data) {
  if (!data) return
  endpoints.value = data.endpoints || []
  bindings.value = data.bindings || []
  slots.value = data.slots || []
  resolved.value = data.resolved || {}
}

async function runAction(action, extra = {}) {
  busy.value = true
  errorText.value = ''
  try {
    const data = await requestLlmConfig(getMessages, { action, ...extra })
    applySnapshot(data)
    statusText.value = `已同步 · ${new Date().toLocaleTimeString('zh-CN')}`
    return data
  } catch (e) {
    errorText.value = llmConfigErrorText(e.code, e.message)
    emit('error', errorText.value)
    throw e
  } finally {
    busy.value = false
  }
}

async function loadConfig() {
  await runAction('llm_config_list')
  if (selectedEndpointId.value && !isNewEndpoint.value) {
    selectEndpoint(selectedEndpointId.value)
  } else if (endpoints.value.length && !isNewEndpoint.value) {
    selectEndpoint(endpoints.value[0].id)
  }
  if (!bindSlot.value && slots.value.length) {
    syncBindFields(slots.value[0].slot_key)
  }
}

function selectEndpoint(id) {
  isNewEndpoint.value = false
  selectedEndpointId.value = id
  const ep = endpoints.value.find((item) => item.id === id)
  if (!ep) return
  form.value = {
    id: ep.id,
    name: ep.name,
    capability: ep.capability,
    base_url: ep.base_url,
    api_key: ep.api_key,
    default_model: ep.default_model,
    timeout: String(ep.timeout ?? ''),
    max_tokens: ep.max_tokens == null ? '' : String(ep.max_tokens),
    temperature: ep.temperature == null ? '' : String(ep.temperature),
    enabled: ep.enabled !== false,
  }
}

function newEndpoint() {
  isNewEndpoint.value = true
  selectedEndpointId.value = ''
  form.value = emptyForm()
  form.value.name = '新模型'
}

function endpointPayload() {
  return {
    name: form.value.name.trim(),
    capability: form.value.capability,
    base_url: form.value.base_url.trim(),
    api_key: form.value.api_key,
    default_model: form.value.default_model.trim(),
    timeout: parseFloat(form.value.timeout) || 120,
    max_tokens: form.value.max_tokens.trim() === '' ? null : parseInt(form.value.max_tokens, 10),
    temperature: form.value.temperature.trim() === '' ? null : parseFloat(form.value.temperature),
    enabled: form.value.enabled,
  }
}

async function saveEndpoint() {
  try {
    const payload = endpointPayload()
    if (isNewEndpoint.value) {
      await runAction('llm_endpoint_create', { endpoint: payload })
      isNewEndpoint.value = false
      const match = endpoints.value.find(
        (ep) => ep.name === payload.name && ep.base_url === payload.base_url,
      )
      if (match) selectEndpoint(match.id)
    } else {
      await runAction('llm_endpoint_update', {
        endpoint_id: form.value.id,
        endpoint: payload,
      })
      selectEndpoint(form.value.id)
    }
  } catch {
    /* errorText 已设置 */
  }
}

async function deleteEndpoint() {
  if (isNewEndpoint.value || !form.value.id) return
  const ep = selectedEndpoint.value
  if (ep?.usage_count > 0) {
    errorText.value = `无法删除：仍被 ${ep.usage_count} 个槽位引用（${(ep.slot_usage || []).join('、')}）`
    return
  }
  if (!window.confirm(`确定删除端点「${form.value.name}」？`)) return
  try {
    await runAction('llm_endpoint_delete', { endpoint_id: form.value.id })
    newEndpoint()
  } catch {
    /* errorText 已设置 */
  }
}

function syncBindFields(slotKey) {
  bindSlot.value = slotKey
  const binding = bindings.value.find((b) => b.slot_key === slotKey)
  bindEndpointId.value = binding?.endpoint_id || ''
  bindModelOverride.value = binding?.model_override || ''
}

function onBindingRowClick(row) {
  syncBindFields(row.slot_key)
}

function compatibleEndpoints(slotKey) {
  const slot = slots.value.find((s) => s.slot_key === slotKey)
  if (!slot) return endpointOptions.value
  return endpointOptions.value.filter((ep) => ep.capability === slot.capability)
}

async function applyBinding() {
  if (!bindSlot.value || !bindEndpointId.value) {
    errorText.value = '请选择槽位和端点'
    return
  }
  try {
    await runAction('llm_binding_upsert', {
      slot_key: bindSlot.value,
      endpoint_id: bindEndpointId.value,
      model_override: bindModelOverride.value.trim() || null,
      clear_model_override: !bindModelOverride.value.trim(),
    })
    syncBindFields(bindSlot.value)
  } catch {
    /* errorText 已设置 */
  }
}

async function clearBindingOverride() {
  if (!bindSlot.value || !bindEndpointId.value) return
  bindModelOverride.value = ''
  await applyBinding()
}

onMounted(async () => {
  try {
    await loadConfig()
  } catch {
    /* errorText 已展示 */
  }
})
</script>

<template>
  <div class="relative flex min-h-0 flex-1 flex-col">
    <div class="shrink-0 border-b border-surface-border bg-slate-500/5 px-4 py-2 md:px-5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p class="text-xs font-medium text-slate-300">LLM 模型配置</p>
          <p class="text-[11px] text-slate-500">
            管理 Local Agent 端点与槽位绑定
            <span :class="live ? 'text-emerald-400' : 'text-amber-400'">
              · {{ live ? 'WebSocket 已连接' : 'WebSocket 未连接' }}
            </span>
          </p>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            class="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-slate-300 hover:bg-surface-raised disabled:opacity-50"
            :disabled="busy"
            @click="loadConfig"
          >
            刷新
          </button>
          <button
            type="button"
            class="rounded-lg bg-violet-600 px-3 py-1.5 text-xs text-white hover:bg-violet-500 disabled:opacity-50"
            :disabled="busy"
            @click="newEndpoint"
          >
            新建端点
          </button>
        </div>
      </div>
      <p v-if="statusText" class="mt-1 text-[11px] text-slate-500">{{ statusText }}</p>
      <p v-if="errorText" class="mt-1 text-[11px] text-red-300">{{ errorText }}</p>
    </div>

    <div class="flex min-h-0 flex-1 flex-col overflow-hidden lg:flex-row">
      <section class="flex min-h-0 flex-col border-b border-surface-border lg:w-2/5 lg:border-b-0 lg:border-r">
        <div class="shrink-0 px-4 py-2 text-[11px] font-medium text-slate-400">模型端点</div>
        <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3 scrollbar-thin">
          <table class="w-full text-left text-xs text-slate-300">
            <thead class="sticky top-0 bg-surface text-slate-500">
              <tr>
                <th class="py-1.5 pr-2">名称</th>
                <th class="py-1.5 pr-2">类型</th>
                <th class="py-1.5 pr-2">模型</th>
                <th class="py-1.5">引用</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="ep in endpoints"
                :key="ep.id"
                class="cursor-pointer border-t border-surface-border/60 hover:bg-surface-raised/60"
                :class="selectedEndpointId === ep.id && !isNewEndpoint ? 'bg-violet-500/10' : ''"
                @click="selectEndpoint(ep.id)"
              >
                <td class="py-2 pr-2">{{ ep.name }}</td>
                <td class="py-2 pr-2">{{ ep.capability }}</td>
                <td class="max-w-[6rem] truncate py-2 pr-2" :title="ep.default_model">{{ ep.default_model }}</td>
                <td class="py-2">{{ ep.usage_count ?? 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="shrink-0 border-t border-surface-border px-4 py-3">
          <p class="mb-2 text-[11px] font-medium text-slate-400">{{ isNewEndpoint ? '新建端点' : '端点详情' }}</p>
          <div class="grid grid-cols-2 gap-2">
            <label class="col-span-2 block">
              <span class="mb-0.5 block text-[10px] text-slate-500">名称</span>
              <input v-model="form.name" class="input-field" />
            </label>
            <label class="block">
              <span class="mb-0.5 block text-[10px] text-slate-500">类型</span>
              <select v-model="form.capability" class="input-field">
                <option value="chat">chat</option>
                <option value="embed">embed</option>
              </select>
            </label>
            <label class="block">
              <span class="mb-0.5 block text-[10px] text-slate-500">默认模型</span>
              <input v-model="form.default_model" class="input-field" />
            </label>
            <label class="col-span-2 block">
              <span class="mb-0.5 block text-[10px] text-slate-500">Base URL</span>
              <input v-model="form.base_url" class="input-field" />
            </label>
            <label class="col-span-2 block">
              <span class="mb-0.5 block text-[10px] text-slate-500">API Key</span>
              <input v-model="form.api_key" class="input-field font-mono" />
            </label>
            <label class="block">
              <span class="mb-0.5 block text-[10px] text-slate-500">Timeout</span>
              <input v-model="form.timeout" class="input-field" />
            </label>
            <label class="block">
              <span class="mb-0.5 block text-[10px] text-slate-500">Max tokens</span>
              <input v-model="form.max_tokens" class="input-field" placeholder="空=不限" />
            </label>
            <label class="block">
              <span class="mb-0.5 block text-[10px] text-slate-500">Temperature</span>
              <input v-model="form.temperature" class="input-field" placeholder="空=默认" />
            </label>
            <label class="flex items-center gap-2 pt-4">
              <input v-model="form.enabled" type="checkbox" class="rounded" />
              <span class="text-[11px] text-slate-400">启用</span>
            </label>
          </div>
          <p v-if="selectedEndpoint?.slot_usage?.length" class="mt-2 text-[10px] text-amber-400/90">
            被引用：{{ selectedEndpoint.slot_usage.join('、') }}
          </p>
          <div class="mt-3 flex gap-2">
            <button
              type="button"
              class="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs text-white hover:bg-emerald-500 disabled:opacity-50"
              :disabled="busy"
              @click="saveEndpoint"
            >
              保存
            </button>
            <button
              type="button"
              class="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
              :disabled="busy || isNewEndpoint"
              @click="deleteEndpoint"
            >
              删除
            </button>
          </div>
        </div>
      </section>

      <section class="flex min-h-0 flex-1 flex-col">
        <div class="shrink-0 px-4 py-2 text-[11px] font-medium text-slate-400">槽位绑定</div>
        <div class="min-h-0 flex-1 overflow-y-auto px-3 pb-3 scrollbar-thin">
          <table class="w-full text-left text-xs text-slate-300">
            <thead class="sticky top-0 bg-surface text-slate-500">
              <tr>
                <th class="py-1.5 pr-2">槽位</th>
                <th class="py-1.5 pr-2">说明</th>
                <th class="py-1.5 pr-2">端点</th>
                <th class="py-1.5 pr-2">覆盖</th>
                <th class="py-1.5 pr-2">实际模型</th>
                <th class="py-1.5">来源</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in bindingRows"
                :key="row.slot_key"
                class="cursor-pointer border-t border-surface-border/60 hover:bg-surface-raised/60"
                :class="bindSlot === row.slot_key ? 'bg-violet-500/10' : ''"
                @click="onBindingRowClick(row)"
              >
                <td class="py-2 pr-2 font-mono text-[10px]">{{ row.slot_key }}</td>
                <td class="py-2 pr-2">{{ row.label }}</td>
                <td class="py-2 pr-2">{{ row.endpoint_name }}</td>
                <td class="py-2 pr-2">{{ row.model_override || '—' }}</td>
                <td class="py-2 pr-2">{{ row.resolved_model }}</td>
                <td class="py-2">{{ row.source }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="shrink-0 border-t border-surface-border px-4 py-3">
          <p class="mb-2 text-[11px] font-medium text-slate-400">修改绑定</p>
          <div class="flex flex-wrap items-end gap-2">
            <label class="block min-w-[8rem]">
              <span class="mb-0.5 block text-[10px] text-slate-500">槽位</span>
              <select v-model="bindSlot" class="input-field" @change="syncBindFields(bindSlot)">
                <option v-for="s in slots" :key="s.slot_key" :value="s.slot_key">{{ s.slot_key }}</option>
              </select>
            </label>
            <label class="block min-w-[10rem] flex-1">
              <span class="mb-0.5 block text-[10px] text-slate-500">端点</span>
              <select v-model="bindEndpointId" class="input-field">
                <option value="">— 选择 —</option>
                <option v-for="ep in compatibleEndpoints(bindSlot)" :key="ep.id" :value="ep.id">
                  {{ ep.label }}
                </option>
              </select>
            </label>
            <label class="block min-w-[8rem]">
              <span class="mb-0.5 block text-[10px] text-slate-500">模型覆盖</span>
              <input v-model="bindModelOverride" class="input-field" placeholder="可选" />
            </label>
            <button
              type="button"
              class="rounded-lg bg-violet-600 px-3 py-1.5 text-xs text-white hover:bg-violet-500 disabled:opacity-50"
              :disabled="busy"
              @click="applyBinding"
            >
              应用绑定
            </button>
            <button
              type="button"
              class="rounded-lg border border-surface-border px-3 py-1.5 text-xs text-slate-300 hover:bg-surface-raised disabled:opacity-50"
              :disabled="busy"
              @click="clearBindingOverride"
            >
              清除覆盖
            </button>
          </div>
        </div>
      </section>
    </div>

    <div v-if="busy" class="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20">
      <span class="rounded-lg bg-surface-raised px-4 py-2 text-sm text-slate-300">处理中…</span>
    </div>
  </div>
</template>

<style scoped>
.input-field {
  @apply w-full rounded-lg border border-surface-border bg-surface-raised px-2.5 py-1.5 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-violet-500/40;
}
</style>
