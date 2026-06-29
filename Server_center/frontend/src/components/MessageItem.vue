<script setup>
import ApprovalCard from './messages/ApprovalCard.vue'
import DesktopScreenshot from './messages/DesktopScreenshot.vue'
import ExecutionLog from './messages/ExecutionLog.vue'
import MemoryRecord from './messages/MemoryRecord.vue'
import PersonaState from './messages/PersonaState.vue'
import PlanResult from './messages/PlanResult.vue'
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
  desktop_screenshot: DesktopScreenshot,
  camera_capture: DesktopScreenshot,
  persona_state: PersonaState,
  rag_result: RagResult,
  plan_result: PlanResult,
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
