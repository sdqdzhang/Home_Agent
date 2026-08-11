<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  fetchExtensions,
  fetchExtensionSettings,
  installExtension,
  resetExtensionSettings,
  saveExtensionSettings,
  uninstallExtension,
} from '../api/client.js'

defineProps({
  agent: { type: Object, required: true },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['error', 'changed'])

const items = ref([])
const busy = ref(false)
const statusText = ref('')
const errorText = ref('')
const fileInput = ref(null)
const purgeData = ref(false)

const configOpen = ref(false)
const configItem = ref(null)
const configFields = ref([])
const configValues = ref({})
const configBusy = ref(false)
const configError = ref('')
const configHint = ref('')

async function refresh() {
  errorText.value = ''
  try {
    const data = await fetchExtensions()
    items.value = data.extensions || []
  } catch (err) {
    const raw = err?.message || String(err)
    errorText.value = /502/.test(raw)
      ? '无法连接 Local Agent（502）。请先启动 Local（venv 下 uvicorn），再刷新。'
      : raw
    items.value = []
    emit('error', errorText.value)
  }
}

async function onPickFile(ev) {
  const file = ev.target?.files?.[0]
  if (!file) return
  busy.value = true
  statusText.value = `正在安装 ${file.name}…`
  errorText.value = ''
  try {
    const result = await installExtension(file)
    statusText.value = `已安装 ${result.module_id}@${result.version}（${result.apply}）`
    if (result.apply === 'restart_required') {
      statusText.value += ' — 请重启 Local Agent 后刷新'
    }
    await refresh()
    emit('changed')
  } catch (err) {
    errorText.value = err?.message || String(err)
    emit('error', errorText.value)
  } finally {
    busy.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function onUninstall(item) {
  const label = item.ui?.label || item.name || item.id
  const ok = window.confirm(
    `确定卸载「${label}」(${item.id})？\n` +
      '将删除 extensions/ 下已安装代码（可再装升级版）。\n' +
      (purgeData.value ? '并删除运行时 data（含模块配置）。\n' : '') +
      'extension_packages/ 开发源码不会被删。',
  )
  if (!ok) return
  busy.value = true
  statusText.value = `正在卸载 ${item.id}…`
  errorText.value = ''
  try {
    const result = await uninstallExtension(item.id, {
      purgeCode: true,
      purgeData: purgeData.value,
    })
    statusText.value = `已卸载 ${result.module_id}（${result.apply}）${result.message ? ' — ' + result.message : ''}`
    if (result.apply === 'restart_required') {
      statusText.value += ' — 请重启 Local Agent 后刷新'
    }
    await refresh()
    emit('changed')
  } catch (err) {
    errorText.value = err?.message || String(err)
    emit('error', errorText.value)
  } finally {
    busy.value = false
  }
}

function statusBadge(item) {
  if (item.loaded) return '运行中'
  if (item.status === 'ready') return '已安装'
  if (item.status === 'error') return '错误'
  return item.status || '未知'
}

function canConfigure(item) {
  return Boolean(item.has_settings || (item.settings_count && item.settings_count > 0))
}

const groupedFields = computed(() => {
  const groups = new Map()
  for (const field of configFields.value) {
    const g = field.group || '常规'
    if (!groups.has(g)) groups.set(g, [])
    groups.get(g).push(field)
  }
  return [...groups.entries()]
})

async function openConfig(item) {
  configItem.value = item
  configOpen.value = true
  configError.value = ''
  configHint.value = ''
  configBusy.value = true
  configFields.value = []
  configValues.value = {}
  try {
    const data = await fetchExtensionSettings(item.id)
    configFields.value = data.fields || []
    configValues.value = { ...(data.values || {}) }
    for (const f of configFields.value) {
      if (f.type === 'multiselect' || f.type === 'checkbox_group') {
        if (!Array.isArray(configValues.value[f.key])) {
          configValues.value[f.key] = []
        }
      }
      if (f.type === 'boolean' && typeof configValues.value[f.key] !== 'boolean') {
        configValues.value[f.key] = Boolean(configValues.value[f.key])
      }
    }
    configHint.value = data.has_user_overrides
      ? '已有用户覆盖；可重置为包默认。'
      : '当前为包内默认，可直接使用；改动后写入 data/<id>/settings.json。'
  } catch (err) {
    configError.value = err?.message || String(err)
  } finally {
    configBusy.value = false
  }
}

function closeConfig() {
  configOpen.value = false
  configItem.value = null
  configError.value = ''
}

function toggleMulti(fieldKey, optionValue, checked) {
  const cur = Array.isArray(configValues.value[fieldKey]) ? [...configValues.value[fieldKey]] : []
  const idx = cur.indexOf(optionValue)
  if (checked && idx < 0) cur.push(optionValue)
  if (!checked && idx >= 0) cur.splice(idx, 1)
  configValues.value[fieldKey] = cur
}

async function saveConfig() {
  if (!configItem.value) return
  configBusy.value = true
  configError.value = ''
  try {
    await saveExtensionSettings(configItem.value.id, { ...configValues.value })
    statusText.value = `已保存 ${configItem.value.id} 配置`
    closeConfig()
    emit('changed')
  } catch (err) {
    configError.value = err?.message || String(err)
  } finally {
    configBusy.value = false
  }
}

async function resetConfig() {
  if (!configItem.value) return
  if (!window.confirm('恢复为包内默认配置？将删除用户覆盖。')) return
  configBusy.value = true
  configError.value = ''
  try {
    const data = await resetExtensionSettings(configItem.value.id)
    configFields.value = data.fields || []
    configValues.value = { ...(data.values || {}) }
    configHint.value = '已恢复包内默认。'
    statusText.value = `已重置 ${configItem.value.id} 配置`
  } catch (err) {
    configError.value = err?.message || String(err)
  } finally {
    configBusy.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-4 md:px-6">
    <div class="mx-auto w-full max-w-3xl space-y-6">
      <section class="space-y-2">
        <h2 class="text-sm font-semibold text-slate-200">安装扩展</h2>
        <p class="text-xs leading-relaxed text-slate-500">
          上传 <code class="text-slate-400">.hamod</code> 安装包（由
          <code class="text-slate-400">python -m shared.extensions pack …</code>
          生成）。模型绑定请到「模型配置」；模块自身参数用下方「配置」。
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <label
            class="inline-flex cursor-pointer items-center rounded-lg bg-slate-100 px-3 py-2 text-sm font-medium text-slate-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
            :class="{ 'pointer-events-none opacity-50': busy }"
          >
            选择 .hamod 文件
            <input
              ref="fileInput"
              type="file"
              accept=".hamod,application/zip"
              class="hidden"
              :disabled="busy"
              @change="onPickFile"
            />
          </label>
          <button
            type="button"
            class="rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-300 hover:border-slate-400 hover:text-white disabled:opacity-50"
            :disabled="busy"
            @click="refresh"
          >
            刷新列表
          </button>
        </div>
      </section>

      <section class="space-y-3">
        <div class="flex flex-wrap items-end justify-between gap-2">
          <h2 class="text-sm font-semibold text-slate-200">已安装</h2>
          <label class="flex items-center gap-2 text-xs text-slate-400">
            <input v-model="purgeData" type="checkbox" class="rounded border-slate-600" />
            卸载时同时删除 data 数据
          </label>
        </div>

        <p v-if="!items.length" class="rounded-lg border border-dashed border-slate-700 px-4 py-8 text-center text-sm text-slate-500">
          暂无已安装扩展
        </p>

        <ul class="space-y-2">
          <li
            v-for="item in items"
            :key="item.id"
            class="flex flex-col gap-3 rounded-xl border border-slate-700/80 bg-slate-900/40 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          >
            <div class="min-w-0 space-y-1">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-base text-slate-200">{{ item.ui?.icon || '◍' }}</span>
                <span class="font-medium text-slate-100">{{ item.ui?.label || item.name || item.id }}</span>
                <span class="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">
                  {{ statusBadge(item) }}
                </span>
                <span v-if="item.bundled" class="rounded bg-amber-900/40 px-1.5 py-0.5 text-[10px] text-amber-200/90">
                  内置路径
                </span>
              </div>
              <p class="truncate text-xs text-slate-500">
                {{ item.id }}@{{ item.version || '?' }}
                <span v-if="item.path"> · {{ item.path }}</span>
              </p>
              <p v-if="item.description" class="text-xs text-slate-400">{{ item.description }}</p>
              <p v-if="item.error" class="text-xs text-red-300">{{ item.error }}</p>
            </div>
            <div class="flex shrink-0 flex-wrap gap-2">
              <button
                v-if="canConfigure(item)"
                type="button"
                class="rounded-lg border border-slate-500/50 px-3 py-1.5 text-sm text-slate-200 hover:border-slate-300 hover:bg-slate-800/60 disabled:opacity-50"
                :disabled="busy"
                @click="openConfig(item)"
              >
                配置
              </button>
              <button
                type="button"
                class="rounded-lg border border-red-500/40 px-3 py-1.5 text-sm text-red-200 hover:bg-red-500/10 disabled:opacity-50"
                :disabled="busy"
                @click="onUninstall(item)"
              >
                卸载
              </button>
            </div>
          </li>
        </ul>
      </section>

      <p v-if="statusText" class="text-xs text-emerald-300/90">{{ statusText }}</p>
      <p v-if="errorText" class="whitespace-pre-wrap text-xs text-red-300">{{ errorText }}</p>
    </div>

    <!-- 配置弹层 -->
    <div
      v-if="configOpen"
      class="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-4 sm:items-center"
      @click.self="closeConfig"
    >
      <div class="flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-950 shadow-xl">
        <div class="flex items-start justify-between gap-3 border-b border-slate-800 px-4 py-3">
          <div>
            <h3 class="text-sm font-semibold text-slate-100">
              配置 · {{ configItem?.ui?.label || configItem?.name || configItem?.id }}
            </h3>
            <p class="mt-1 text-xs text-slate-500">
              模型请到「模型配置」绑定槽位。此处为模块自身参数。
            </p>
          </div>
          <button type="button" class="text-slate-400 hover:text-white" @click="closeConfig">✕</button>
        </div>

        <div class="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
          <p v-if="configHint" class="text-xs text-slate-500">{{ configHint }}</p>
          <p v-if="configBusy && !configFields.length" class="text-sm text-slate-400">加载中…</p>
          <p v-else-if="!configFields.length && !configBusy" class="text-sm text-slate-500">该扩展未声明可配置项。</p>

          <section v-for="[group, fields] in groupedFields" :key="group" class="space-y-3">
            <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-400">{{ group }}</h4>
            <div v-for="field in fields" :key="field.key" class="space-y-1.5">
              <label class="block text-sm text-slate-200">
                {{ field.label || field.key }}
                <span v-if="field.required" class="text-red-400">*</span>
              </label>
              <p v-if="field.description" class="text-xs text-slate-500">{{ field.description }}</p>

              <input
                v-if="field.type === 'string' || field.type === 'secret'"
                v-model="configValues[field.key]"
                :type="field.type === 'secret' ? 'password' : 'text'"
                :placeholder="field.placeholder || ''"
                class="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />

              <textarea
                v-else-if="field.type === 'text'"
                v-model="configValues[field.key]"
                rows="3"
                :placeholder="field.placeholder || ''"
                class="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />

              <input
                v-else-if="field.type === 'number' || field.type === 'integer'"
                v-model.number="configValues[field.key]"
                type="number"
                :min="field.min ?? undefined"
                :max="field.max ?? undefined"
                :step="field.step ?? (field.type === 'integer' ? 1 : 'any')"
                class="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              />

              <label
                v-else-if="field.type === 'boolean'"
                class="flex items-center gap-2 text-sm text-slate-300"
              >
                <input v-model="configValues[field.key]" type="checkbox" class="rounded border-slate-600" />
                启用
              </label>

              <select
                v-else-if="field.type === 'select'"
                v-model="configValues[field.key]"
                class="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-500"
              >
                <option v-for="opt in field.options || []" :key="opt.value" :value="opt.value">
                  {{ opt.label || opt.value }}
                </option>
              </select>

              <div v-else-if="field.type === 'radio'" class="space-y-1.5">
                <label
                  v-for="opt in field.options || []"
                  :key="opt.value"
                  class="flex items-center gap-2 text-sm text-slate-300"
                >
                  <input
                    v-model="configValues[field.key]"
                    type="radio"
                    :value="opt.value"
                    class="border-slate-600"
                  />
                  {{ opt.label || opt.value }}
                </label>
              </div>

              <div v-else-if="field.type === 'multiselect' || field.type === 'checkbox_group'" class="space-y-1.5">
                <label
                  v-for="opt in field.options || []"
                  :key="opt.value"
                  class="flex items-center gap-2 text-sm text-slate-300"
                >
                  <input
                    type="checkbox"
                    class="rounded border-slate-600"
                    :checked="(configValues[field.key] || []).includes(opt.value)"
                    @change="toggleMulti(field.key, opt.value, $event.target.checked)"
                  />
                  {{ opt.label || opt.value }}
                </label>
              </div>

              <p v-else class="text-xs text-amber-300">不支持的控件类型：{{ field.type }}</p>
            </div>
          </section>

          <p v-if="configError" class="whitespace-pre-wrap text-xs text-red-300">{{ configError }}</p>
        </div>

        <div class="flex flex-wrap justify-end gap-2 border-t border-slate-800 px-4 py-3">
          <button
            type="button"
            class="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-400 disabled:opacity-50"
            :disabled="configBusy"
            @click="resetConfig"
          >
            恢复默认
          </button>
          <button
            type="button"
            class="rounded-lg border border-slate-600 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-400"
            :disabled="configBusy"
            @click="closeConfig"
          >
            取消
          </button>
          <button
            type="button"
            class="rounded-lg bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-900 hover:bg-white disabled:opacity-50"
            :disabled="configBusy || !configFields.length"
            @click="saveConfig"
          >
            保存
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
