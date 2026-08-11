<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

const imageSrc = (msg) => {
  const b64 = msg.message?.image_base64
  if (!b64) return ''
  const fmt = msg.message?.format || 'jpeg'
  return `data:image/${fmt};base64,${b64}`
}
</script>

<template>
  <div class="w-full max-w-3xl">
    <div class="overflow-hidden rounded-xl border border-slate-700/60 bg-slate-800/40">
      <div class="flex items-center justify-between border-b border-slate-700/50 px-3 py-2 text-xs text-slate-400">
        <span>{{ msg.msg_type === 'camera_capture' ? '摄像头拍照' : '远程桌面截图' }} · [{{ formatTime(msg.timestamp) }}]</span>
        <span v-if="msg.message?.width">
          {{ msg.message.width }}×{{ msg.message.height }}
        </span>
      </div>
      <img
        v-if="imageSrc(msg)"
        :src="imageSrc(msg)"
        :alt="msg.msg_type === 'camera_capture' ? '摄像头拍照' : '远程桌面截图'"
        class="max-h-[70vh] w-full object-contain bg-black"
      />
      <p
        v-else-if="msg.message?.status === 'error' || msg.message?.ok === false"
        class="p-4 text-center text-sm text-rose-300"
      >
        {{ msg.message?.text || msg.message?.error || '拍照失败' }}
      </p>
      <p v-else-if="msg.message?.status === 'running'" class="p-4 text-center text-sm text-slate-500">
        {{ msg.message?.text || '处理中…' }}
      </p>
      <p v-else class="p-4 text-center text-sm text-slate-500">截图数据不可用</p>
    </div>
  </div>
</template>
