import { nextTick, onMounted, ref, watch } from 'vue'

const NEAR_BOTTOM_PX = 96

function isNearBottom(el) {
  if (!el) return true
  return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_PX
}

/**
 * 对话列表滚到底部；仅在用户已在底部附近时随新消息自动滚动（避免轮询把阅读位置拉走）。
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
      const el = listEl.value
      if (!isNearBottom(el)) return
      scrollToBottom()
    },
    { deep: true },
  )

  onMounted(() => scrollToBottom(false))

  return { listEl, scrollToBottom }
}
