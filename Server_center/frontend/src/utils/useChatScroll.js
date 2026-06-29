import { nextTick, onMounted, ref, watch } from 'vue'

/**
 * 对话列表自动滚到底部。
 * @param {import('vue').WatchSource<unknown[]>} messagesSource
 */
export function useChatScroll(messagesSource) {
  const listEl = ref(null)

  async function scrollToBottom(smooth = true) {
    await nextTick()
    const el = listEl.value
    if (!el) return
    requestAnimationFrame(() => {
      const target = listEl.value
      if (!target) return
      target.scrollTo({
        top: target.scrollHeight,
        behavior: smooth ? 'smooth' : 'auto',
      })
    })
  }

  watch(
    messagesSource,
    (msgs) => {
      if (!msgs?.length) return
      scrollToBottom()
    },
    { deep: true },
  )

  onMounted(() => scrollToBottom(false))

  return { listEl, scrollToBottom }
}
