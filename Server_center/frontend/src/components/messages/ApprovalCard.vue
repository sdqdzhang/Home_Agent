<script setup>
import { ref } from 'vue'
import { respondMessage } from '../../api/client.js'

const props = defineProps({
  msg: { type: Object, required: true },
})

const emit = defineEmits(['responded'])
const submitting = ref(false)
const reason = ref('')

async function submit(approved) {
  submitting.value = true
  try {
    const result = await respondMessage(props.msg.id, approved, reason.value)
    emit('responded', result.message)
  } catch (e) {
    alert(e.message)
  } finally {
    submitting.value = false
  }
}

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleString('zh-CN')
}

const command = () =>
  props.msg.message?.payload?.command ||
  props.msg.message?.command ||
  props.msg.message?.text ||
  ''
</script>

<template>
  <div class="w-full max-w-2xl">
    <div
      class="overflow-hidden rounded-xl border-2 shadow-lg"
      :class="
        msg.status === 'pending'
          ? 'border-amber-500/70 bg-amber-500/5 shadow-amber-500/10'
          : 'border-red-500/40 bg-red-500/5'
      "
    >
      <div class="border-b border-amber-500/20 bg-amber-500/10 px-4 py-2 text-sm font-semibold text-amber-200">
        ⚠ 安全审批请求
        <span v-if="msg.status && msg.status !== 'pending'" class="ml-2 text-xs font-normal opacity-80">
          ({{ msg.status === 'approved' ? '已批准' : '已拒绝' }})
        </span>
      </div>

      <div class="space-y-3 px-4 py-4">
        <p class="text-sm leading-relaxed text-slate-200">{{ msg.message?.text }}</p>

        <pre
          v-if="command()"
          class="overflow-x-auto rounded-lg border border-red-500/30 bg-black/60 px-4 py-3 font-mono text-sm text-red-300"
        >{{ command() }}</pre>

        <p class="text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>

        <div v-if="msg.status === 'pending'" class="space-y-3 pt-1">
          <input
            v-model="reason"
            type="text"
            placeholder="备注（可选）"
            class="w-full rounded-lg border border-surface-border bg-surface px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
          />
          <div class="grid grid-cols-2 gap-3">
            <button
              type="button"
              class="rounded-xl bg-emerald-600 py-4 text-base font-bold text-white transition hover:bg-emerald-500 disabled:opacity-50"
              :disabled="submitting"
              @click="submit(true)"
            >
              ✓ 批准
            </button>
            <button
              type="button"
              class="rounded-xl bg-red-600 py-4 text-base font-bold text-white transition hover:bg-red-500 disabled:opacity-50"
              :disabled="submitting"
              @click="submit(false)"
            >
              ✕ 拒绝
            </button>
          </div>
        </div>

        <div v-else-if="msg.response" class="rounded-lg bg-slate-800/80 px-3 py-2 text-xs text-slate-300">
          回复：{{ msg.response.reason || (msg.response.approved ? '已批准' : '已拒绝') }}
        </div>
      </div>
    </div>
  </div>
</template>
