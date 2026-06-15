<script setup>
defineProps({
  agent: { type: Object, required: true },
})
</script>

<template>
  <div class="flex flex-col items-center justify-center px-6 py-16 text-center">
    <span class="text-4xl">{{ agent.icon }}</span>
    <h3 class="mt-3 text-base font-medium text-slate-200">{{ agent.label }}</h3>
    <p class="mt-2 max-w-sm text-sm leading-relaxed text-slate-500">{{ agent.description }}</p>
    <p class="mt-4 text-xs text-slate-600">
      等待模块推送 · 常用类型：
      <span class="text-slate-500">{{ agent.defaultMsgTypes?.join(', ') }}</span>
    </p>
  </div>
</template>
