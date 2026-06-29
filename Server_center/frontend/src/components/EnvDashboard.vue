<script setup>
import { computed } from 'vue'
import { extractEnvDashboard } from '../utils/messages.js'

const props = defineProps({
  messages: { type: Array, required: true },
  agent: { type: Object, required: true },
  live: { type: Boolean, default: false },
})

const dash = computed(() => extractEnvDashboard(props.messages, props.agent))

function formatTime(ts) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('zh-CN')
}
</script>

<template>
  <section
    class="shrink-0 border-b border-surface-border bg-surface-raised/80 px-4 py-3 md:px-6"
    :class="dash.alert ? 'ring-1 ring-inset ring-red-500/30' : ''"
  >
    <div class="mx-auto max-w-3xl">
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <h2 class="text-sm font-semibold text-slate-200">系统状态</h2>
          <span
            v-if="live"
            class="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300"
          >
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            实时
          </span>
          <span
            v-if="dash.alert"
            class="rounded-full bg-red-500/25 px-2 py-0.5 text-[10px] font-semibold text-red-200"
          >
            告警
          </span>
        </div>
        <span class="text-[10px] text-slate-500">更新 {{ formatTime(dash.updated_at) }}</span>
      </div>

      <p v-if="dash.alert_reason" class="mb-2 text-xs text-red-300">{{ dash.alert_reason }}</p>

      <div v-if="!dash.snapshot && !dash.llm_summary?.summary" class="py-6 text-center text-sm text-slate-500">
        等待环境感知上报…
      </div>

      <div v-else class="max-h-[42vh] space-y-3 overflow-y-auto scrollbar-thin pr-1">
        <!-- LLM 总结 -->
        <div
          v-if="dash.llm_summary?.summary"
          class="rounded-xl border border-indigo-500/25 bg-indigo-500/10 px-3 py-2.5"
        >
          <div class="mb-1 flex items-center justify-between gap-2">
            <span class="text-[10px] font-semibold uppercase tracking-wide text-indigo-300">运营总结</span>
            <span v-if="dash.llm_summary.health_score != null" class="text-[10px] text-indigo-200/80">
              健康 {{ dash.llm_summary.health_score }}
              <span v-if="dash.llm_summary.source"> · {{ dash.llm_summary.source }}</span>
            </span>
          </div>
          <p class="text-sm leading-relaxed text-slate-200">{{ dash.llm_summary.summary }}</p>
          <p v-if="dash.summary_time" class="mt-1 text-[10px] text-slate-500">
            总结于 {{ formatTime(dash.summary_time) }}
          </p>
        </div>

        <!-- 实时快照 -->
        <div
          v-if="dash.snapshot"
          class="rounded-xl border border-slate-700/60 bg-slate-800/50 px-3 py-2.5 text-xs"
        >
          <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span class="text-[10px] font-semibold uppercase tracking-wide text-slate-500">最新快照</span>
            <span class="text-[10px] text-slate-500">
              收到于 {{ formatTime(dash.snapshot_time) || dash.snapshot.timestamp_iso || '—' }}
            </span>
          </div>

          <div class="grid gap-2 sm:grid-cols-2">
            <div class="rounded-lg bg-slate-900/50 p-2">
              <div class="text-[10px] text-slate-500">CPU / 内存</div>
              <div class="font-mono text-slate-200">
                {{ dash.snapshot.cpu_percent }}% / {{ dash.snapshot.memory_percent }}%
                <span class="text-slate-500">
                  ({{ dash.snapshot.memory_used_gb }}/{{ dash.snapshot.memory_total_gb }} GB)
                </span>
              </div>
            </div>
            <div v-if="dash.snapshot.network" class="rounded-lg bg-slate-900/50 p-2">
              <div class="text-[10px] text-slate-500">网络</div>
              <div class="font-mono text-slate-200">
                ↑{{ dash.snapshot.network.upload_mbps }}
                ↓{{ dash.snapshot.network.download_mbps }} MB/s
              </div>
              <div class="text-slate-400">
                <template v-if="dash.snapshot.network.ping?.skipped">
                  Ping 未测（有效回复不足）
                </template>
                <template v-else>
                  Ping {{ dash.snapshot.network.ping?.latency_ms }}ms ·
                  丢包 {{ dash.snapshot.network.ping?.packet_loss_percent }}%
                </template>
                · {{ dash.snapshot.network.proxy_enabled ? '代理开' : '代理关' }}
                / {{ dash.snapshot.network.vpn_active ? 'VPN开' : 'VPN关' }}
              </div>
            </div>
          </div>

          <div v-if="dash.snapshot.disks?.length" class="mt-2 rounded-lg bg-slate-900/50 p-2">
            <div class="text-[10px] text-slate-500">磁盘</div>
            <div
              v-for="disk in dash.snapshot.disks"
              :key="disk.mountpoint"
              class="font-mono text-slate-300"
            >
              {{ disk.mountpoint }} — {{ disk.used_gb }}/{{ disk.total_gb }} GB ({{ disk.percent }}%)
            </div>
          </div>

          <div v-if="dash.snapshot.top_processes?.length" class="mt-2 rounded-lg bg-slate-900/50 p-2">
            <div class="text-[10px] text-slate-500">Top 进程</div>
            <div
              v-for="proc in dash.snapshot.top_processes"
              :key="`${proc.pid}-${proc.name}`"
              class="font-mono text-slate-300"
            >
              {{ proc.name }} ({{ proc.pid }}) — CPU {{ proc.cpu_percent }}% · MEM {{ proc.memory_percent }}%
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
