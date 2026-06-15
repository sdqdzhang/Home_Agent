<script setup>
import ApprovalCard from './messages/ApprovalCard.vue'
import ExecutionLog from './messages/ExecutionLog.vue'
import MemoryRecord from './messages/MemoryRecord.vue'
import PersonaState from './messages/PersonaState.vue'
import RagResult from './messages/RagResult.vue'
import ReflectionNote from './messages/ReflectionNote.vue'
import SystemStatus from './messages/SystemStatus.vue'
import TextBubble from './messages/TextBubble.vue'

defineProps({
  msg: { type: Object, required: true },
})

defineEmits(['responded'])

const renderers = {
  text: TextBubble,
  approval_request: ApprovalCard,
  execution_log: ExecutionLog,
  system_status: SystemStatus,
  persona_state: PersonaState,
  rag_result: RagResult,
  reflection_note: ReflectionNote,
  memory_record: MemoryRecord,
}

function resolveComponent(msg) {
  return renderers[msg.msg_type] || TextBubble
}
</script>

<template>
  <component
    :is="resolveComponent(msg)"
    :msg="msg"
    @responded="$emit('responded', $event)"
  />
</template>
