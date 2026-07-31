<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { respondClarify } from '../../api/client.js'

const OTHER_LABEL = '其他'

const props = defineProps({
  msg: { type: Object, required: true },
})

const emit = defineEmits(['responded'])
const submitting = ref(false)

const questions = computed(() => {
  const list = props.msg.message?.questions
  return Array.isArray(list) ? list : []
})

/** @type {import('vue').Reactive<Record<string, { choice: string, other: string }>>} */
const answers = reactive({})

function ensureAnswer(qid) {
  if (!answers[qid]) {
    answers[qid] = { choice: '', other: '' }
  }
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

async function submit() {
  if (!allAnswered() || submitting.value) return
  submitting.value = true
  try {
    const payload = {
      session_id: props.msg.message?.session_id || 'default',
      request_id: props.msg.message?.request_id || '',
      answers: questions.value.map((q) => ({
        question_id: q.id,
        answer: resolvedAnswer(q),
        question: q.prompt || '',
      })),
    }
    const result = await respondClarify(props.msg.id, payload)
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

const answeredSummary = computed(() => {
  const resp = props.msg.response
  if (!resp?.answers?.length) return ''
  return resp.answers.map((a) => a.answer).filter(Boolean).join('；')
})
</script>

<template>
  <div class="w-full max-w-2xl">
    <div
      class="overflow-hidden rounded-xl border-2 shadow-lg"
      :class="
        msg.status === 'pending'
          ? 'border-sky-500/70 bg-sky-500/5 shadow-sky-500/10'
          : 'border-slate-500/40 bg-slate-500/5'
      "
    >
      <div class="border-b border-sky-500/20 bg-sky-500/10 px-4 py-2 text-sm font-semibold text-sky-200">
        规划质询
        <span v-if="msg.status && msg.status !== 'pending'" class="ml-2 text-xs font-normal opacity-80">
          （已回答）
        </span>
      </div>

      <div class="space-y-4 px-4 py-4">
        <p v-if="msg.message?.goal" class="text-xs text-slate-500">
          目标：{{ msg.message.goal }}
        </p>

        <div v-for="q in questions" :key="q.id" class="space-y-2">
          <p class="text-sm font-medium text-slate-200">{{ q.prompt }}</p>
          <p v-if="q.reason" class="text-xs text-slate-500">原因：{{ q.reason }}</p>

          <template v-if="msg.status === 'pending'">
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
          </template>
        </div>

        <p class="text-xs text-slate-500">{{ formatTime(msg.timestamp) }}</p>

        <button
          v-if="msg.status === 'pending'"
          type="button"
          class="w-full rounded-xl bg-sky-600 py-3 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:opacity-50"
          :disabled="submitting || !allAnswered()"
          @click="submit"
        >
          提交回答
        </button>

        <div v-else-if="answeredSummary" class="rounded-lg bg-slate-800/80 px-3 py-2 text-xs text-slate-300">
          已选：{{ answeredSummary }}
        </div>
      </div>
    </div>
  </div>
</template>
