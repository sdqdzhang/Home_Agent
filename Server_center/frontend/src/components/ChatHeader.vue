<script setup>
defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  mood: { type: String, default: '平静' },
  globalMood: { type: String, default: null },
  icon: { type: String, default: '💬' },
  showBack: { type: Boolean, default: false },
})

defineEmits(['back'])
</script>

<template>
  <header class="border-b border-surface-border bg-surface-raised px-4 py-3">
    <div class="flex items-center gap-3">
      <button
        v-if="showBack"
        type="button"
        class="flex h-9 w-9 items-center justify-center rounded-lg text-slate-300 hover:bg-white/10 md:hidden"
        aria-label="返回列表"
        @click="$emit('back')"
      >
        <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <span class="text-xl">{{ icon }}</span>

      <div class="min-w-0 flex-1">
        <h1 class="truncate text-base font-semibold text-slate-100">{{ title }}</h1>
        <p v-if="subtitle" class="truncate text-xs text-slate-500">{{ subtitle }}</p>
      </div>

      <div class="flex shrink-0 flex-col items-end gap-0.5 text-right">
        <span class="rounded-full bg-slate-800 px-3 py-1 text-xs text-slate-300">{{ mood }}</span>
        <span v-if="globalMood" class="text-[10px] text-pink-300/80">全局 · {{ globalMood }}</span>
      </div>
    </div>
  </header>
</template>
