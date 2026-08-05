<script setup>
import { computed } from 'vue'
import { isUserMessage } from '../../utils/messages.js'
import { renderMarkdown } from '../../utils/markdown.js'

const props = defineProps({
  msg: { type: Object, required: true },
})

const isUser = computed(() => isUserMessage(props.msg))

/** 仅助手主对话文本走 Markdown；用户气泡与其它 msg_type 保持纯文本 */
const useMarkdown = computed(() => !isUser.value && props.msg.msg_type === 'text')

const plainText = computed(() => props.msg.message?.text || '(空消息)')

const html = computed(() => {
  if (!useMarkdown.value) return ''
  const text = props.msg.message?.text
  if (!text) return '<p>(空消息)</p>'
  return renderMarkdown(text)
})
</script>

<template>
  <div class="flex w-full" :class="isUser ? 'justify-end' : 'justify-start'">
    <div
      class="max-w-[min(85%,36rem)] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm"
      :class="
        isUser
          ? 'rounded-br-md bg-agent-user text-white'
          : 'rounded-bl-md bg-agent-bubble text-slate-100'
      "
    >
      <div
        v-if="useMarkdown"
        class="chat-md"
        v-html="html"
      />
      <p v-else class="whitespace-pre-wrap">{{ plainText }}</p>
      <div
        v-if="msg.message?.attachments?.length"
        class="mt-2 space-y-1 border-t border-white/10 pt-2 text-xs opacity-90"
      >
        <div v-for="(f, i) in msg.message.attachments" :key="i">📎 {{ f.name }} ({{ f.size }})</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-md :deep(> :first-child) {
  margin-top: 0;
}
.chat-md :deep(> :last-child) {
  margin-bottom: 0;
}
.chat-md :deep(p) {
  margin: 0.45em 0;
}
.chat-md :deep(p + p) {
  margin-top: 0.65em;
}
.chat-md :deep(h1),
.chat-md :deep(h2),
.chat-md :deep(h3),
.chat-md :deep(h4) {
  font-weight: 600;
  line-height: 1.35;
  margin: 0.75em 0 0.35em;
  color: #f1f5f9;
}
.chat-md :deep(h1) {
  font-size: 1.15em;
}
.chat-md :deep(h2) {
  font-size: 1.08em;
}
.chat-md :deep(h3),
.chat-md :deep(h4) {
  font-size: 1em;
}
.chat-md :deep(strong),
.chat-md :deep(b) {
  font-weight: 600;
  color: #f8fafc;
}
.chat-md :deep(em),
.chat-md :deep(i) {
  font-style: italic;
  color: #e2e8f0;
}
.chat-md :deep(ul),
.chat-md :deep(ol) {
  margin: 0.45em 0;
  padding-left: 1.25em;
}
.chat-md :deep(ul) {
  list-style: disc;
}
.chat-md :deep(ol) {
  list-style: decimal;
}
.chat-md :deep(li) {
  margin: 0.2em 0;
}
.chat-md :deep(li > ul),
.chat-md :deep(li > ol) {
  margin: 0.15em 0;
}
.chat-md :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.15em 0 0.15em 0.75em;
  border-left: 3px solid rgba(148, 163, 184, 0.45);
  color: #cbd5e1;
}
.chat-md :deep(hr) {
  margin: 0.75em 0;
  border: 0;
  border-top: 1px solid rgba(148, 163, 184, 0.25);
}
.chat-md :deep(a) {
  color: #a5b4fc;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.chat-md :deep(a:hover) {
  color: #c7d2fe;
}
.chat-md :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
  padding: 0.1em 0.35em;
  border-radius: 0.3em;
  background: rgba(15, 17, 23, 0.55);
  color: #e2e8f0;
}
.chat-md :deep(pre) {
  margin: 0.55em 0;
  padding: 0.65em 0.75em;
  overflow-x: auto;
  border-radius: 0.5em;
  background: rgba(15, 17, 23, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.15);
}
.chat-md :deep(pre code) {
  padding: 0;
  background: transparent;
  font-size: 0.85em;
  line-height: 1.45;
  white-space: pre;
}
.chat-md :deep(.md-table-wrap) {
  margin: 0.55em 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.chat-md :deep(table) {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.9em;
}
.chat-md :deep(th),
.chat-md :deep(td) {
  padding: 0.35em 0.55em;
  border: 1px solid rgba(148, 163, 184, 0.25);
  text-align: left;
}
.chat-md :deep(th) {
  background: rgba(15, 17, 23, 0.45);
  font-weight: 600;
  color: #f1f5f9;
}
.chat-md :deep(td) {
  color: #e2e8f0;
}
</style>
