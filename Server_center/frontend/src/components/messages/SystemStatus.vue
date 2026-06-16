<script setup>
defineProps({
  msg: { type: Object, required: true },
})

function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString('zh-CN')
}

function reportLabel(type) {
  const map = {
    snapshot: '实时快照',
    summary: '周期总结',
    alert: '告警',
    alert_cleared: '告警解除',
  }
  return map[type] || '状态更新'
}
</script>

<template>
  <div class="w-full">
    <div
      class="mx-auto max-w-2xl rounded-xl border px-4 py-3 text-left text-xs"
      :class="
        msg.message?.alert
          ? 'border-red-500/40 bg-red-500/10 text-red-100'
          : 'border-slate-700/60 bg-slate-800/40 text-slate-400'
      "
    >
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <span class="text-slate-500">[{{ formatTime(msg.timestamp) }}]</span>
        <span
          v-if="msg.message?.report_type"
          class="rounded bg-slate-700/80 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-300"
        >
          {{ reportLabel(msg.message.report_type) }}
        </span>
        <span
          v-if="msg.message?.alert"
          class="rounded bg-red-500/30 px-2 py-0.5 text-[10px] font-semibold text-red-200"
        >
          告警
        </span>
      </div>

      <p v-if="msg.message?.text" class="mb-2 leading-relaxed text-slate-300">
        {{ msg.message.text }}
      </p>
      <p v-if="msg.message?.alert && msg.message?.alert_reason" class="mb-2 text-red-300">
        {{ msg.message.alert_reason }}
      </p>

      <div v-if="msg.message?.snapshot" class="grid gap-2 sm:grid-cols-2">
        <div class="rounded-lg bg-slate-900/50 p-2">
          <div class="text-[10px] text-slate-500">CPU / 内存</div>
          <div class="font-mono text-slate-200">
            {{ msg.message.snapshot.cpu_percent }}% /
            {{ msg.message.snapshot.memory_percent }}%
            <span class="text-slate-500">
              ({{ msg.message.snapshot.memory_used_gb }}/{{ msg.message.snapshot.memory_total_gb }} GB)
            </span>
          </div>
        </div>

        <div v-if="msg.message.snapshot.network" class="rounded-lg bg-slate-900/50 p-2">
          <div class="text-[10px] text-slate-500">网络</div>
          <div class="font-mono text-slate-200">
            ↑{{ msg.message.snapshot.network.upload_mbps }}
            ↓{{ msg.message.snapshot.network.download_mbps }} MB/s
          </div>
          <div class="text-slate-400">
            Ping {{ msg.message.snapshot.network.ping?.latency_ms }}ms ·
            丢包 {{ msg.message.snapshot.network.ping?.packet_loss_percent }}%
            · {{ msg.message.snapshot.network.proxy_enabled ? '代理开' : '代理关' }}
            / {{ msg.message.snapshot.network.vpn_active ? 'VPN开' : 'VPN关' }}
          </div>
        </div>
      </div>

      <div
        v-if="msg.message?.snapshot?.disks?.length"
        class="mt-2 rounded-lg bg-slate-900/50 p-2"
      >
        <div class="text-[10px] text-slate-500">磁盘</div>
        <div
          v-for="disk in msg.message.snapshot.disks"
          :key="disk.mountpoint"
          class="font-mono text-slate-300"
        >
          {{ disk.mountpoint }} — {{ disk.used_gb }}/{{ disk.total_gb }} GB ({{ disk.percent }}%)
        </div>
      </div>

      <div
        v-if="msg.message?.snapshot?.top_processes?.length"
        class="mt-2 rounded-lg bg-slate-900/50 p-2"
      >
        <div class="text-[10px] text-slate-500">Top 进程</div>
        <div
          v-for="proc in msg.message.snapshot.top_processes"
          :key="`${proc.pid}-${proc.name}`"
          class="font-mono text-slate-300"
        >
          {{ proc.name }} ({{ proc.pid }}) — CPU {{ proc.cpu_percent }}% · MEM {{ proc.memory_percent }}%
        </div>
      </div>

      <div v-if="msg.message?.llm_summary?.health_score != null" class="mt-2 text-slate-400">
        健康评分 {{ msg.message.llm_summary.health_score }}
        <span v-if="msg.message.llm_summary.source"> · {{ msg.message.llm_summary.source }}</span>
      </div>
    </div>
  </div>
</template>
