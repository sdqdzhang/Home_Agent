<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  msg: { type: Object, required: true },
})

const open = ref(false)

const text = computed(() => {
  const t = props.msg.message?.text
  return typeof t === 'string' ? t : ''
})

const preview = computed(() => {
  const t = text.value.trim()
  if (!t) return '继续处理中…'
  const one = t.split(/\n/)[0] || t
  return one.length > 48 ? `${one.slice(0, 48)}…` : one
})
</script>

<template>
  <div class="flex w-full justify-start">
    <div class="max-w-[min(85%,36rem)] text-xs leading-relaxed text-slate-400">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-left transition hover:bg-white/5 hover:text-slate-300"
        :aria-expanded="open"
        @click="open = !open"
      >
        <span
          class="inline-block text-[10px] transition-transform"
          :class="open ? 'rotate-90' : ''"
        >▸</span>
        <span class="font-medium tracking-wide text-slate-500">思考过程</span>
        <span v-if="!open" class="truncate opacity-80">{{ preview }}</span>
      </button>
      <div
        v-if="open"
        class="mt-1 whitespace-pre-wrap rounded-lg border border-white/5 bg-black/20 px-3 py-2 text-[12px] leading-relaxed text-slate-400"
      >
        {{ text || '（无内容）' }}
      </div>
    </div>
  </div>
</template>
