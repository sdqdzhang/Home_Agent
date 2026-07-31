<script setup>
import ApprovalCard from './messages/ApprovalCard.vue'
import ClarifyCard from './messages/ClarifyCard.vue'
import DesktopScreenshot from './messages/DesktopScreenshot.vue'
import ExecutionLog from './messages/ExecutionLog.vue'
import MemoryRecord from './messages/MemoryRecord.vue'
import PersonaState from './messages/PersonaState.vue'
import PlanResult from './messages/PlanResult.vue'
import PlanningSessionCard from './messages/PlanningSessionCard.vue'
import RagResult from './messages/RagResult.vue'
import DataBlockResult from './messages/DataBlockResult.vue'
import SystemStatus from './messages/SystemStatus.vue'
import TextBubble from './messages/TextBubble.vue'

defineProps({
  msg: { type: Object, required: true },
})

defineEmits(['responded'])

const renderers = {
  text: TextBubble,
  tool_result: TextBubble,
  approval_request: ApprovalCard,
  clarify_request: ClarifyCard,
  planning_session: PlanningSessionCard,
  execution_log: ExecutionLog,
  system_status: SystemStatus,
  desktop_screenshot: DesktopScreenshot,
  camera_capture: DesktopScreenshot,
  persona_state: PersonaState,
  rag_result: RagResult,
  plan_result: PlanResult,
  clarify_result: TextBubble,
  env_probe_result: TextBubble,
  plan_progress: TextBubble,
  graph_run_result: TextBubble,
  datablock: DataBlockResult,
  memory_record: MemoryRecord,
  cm_snapshot: TextBubble,
  cm_event: TextBubble,
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
