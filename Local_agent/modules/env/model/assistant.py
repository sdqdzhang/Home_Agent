from __future__ import annotations

import json
from typing import Any

from modules.env.config import env_settings
from shared.llm.client import LLMClient

SYSTEM_PROMPT = """你是远程服务器运维助手。根据压缩后的系统监控 JSON，用中文写一段简洁的运营状况总结（3-6 句）。
同时判断是否存在需要人工关注的异常（CPU/内存持续过高、磁盘将满、网络严重丢包或延迟、异常进程等）。

必须只输出 JSON，格式：
{
  "summary": "运营总结文本",
  "alert": false,
  "alert_reason": "",
  "health_score": 85
}

alert 为 true 时 alert_reason 必填；health_score 为 0-100 整数。"""


CHAT_SYSTEM_PROMPT = """你是环境感知模块的运维助手。根据提供的最新系统状态 JSON（含 snapshot、aggregated、llm_summary）回答用户问题。
回答简洁专业，用中文。若数据不足以回答，请说明缺少什么。"""


class EnvAssistant:
    """环境感知模块 LLM 助手：每次总结使用全新对话。"""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def summarize(self, aggregated: dict[str, Any], *, use_model: bool = True) -> dict[str, Any]:
        if not use_model:
            return self._rule_only_summary(aggregated)

        user_content = json.dumps(aggregated, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是过去窗口内的压缩监控数据：\n{user_content}"},
        ]
        try:
            result = await self.llm.chat_json(
                messages,
                model=env_settings.llm_model,
                temperature=env_settings.llm_temperature,
            )
            return {
                "summary": str(result.get("summary", "")),
                "alert": bool(result.get("alert")),
                "alert_reason": str(result.get("alert_reason") or ""),
                "health_score": int(result.get("health_score") or 0),
                "source": "llm",
            }
        except Exception as exc:
            fallback = self._rule_only_summary(aggregated)
            fallback["llm_error"] = str(exc)
            return fallback

    def _rule_only_summary(self, aggregated: dict[str, Any]) -> dict[str, Any]:
        cpu = aggregated.get("cpu_percent") or {}
        mem = aggregated.get("memory_percent") or {}
        ping = (aggregated.get("network") or {}).get("ping") or {}
        loss = ping.get("packet_loss_percent") or {}
        latency = ping.get("latency_ms") or {}
        disks = aggregated.get("disks") or []

        parts = [
            f"CPU 均值 {cpu.get('avg')}%（峰 {cpu.get('max')}%）",
            f"内存均值 {mem.get('avg')}%（峰 {mem.get('max')}%）",
        ]
        if latency.get("avg") is not None:
            parts.append(f"Ping 延迟均值 {latency.get('avg')}ms，丢包 {loss.get('avg')}%")

        alert, reason = False, ""
        if (cpu.get("max") or 0) >= env_settings.cpu_alert_percent:
            alert, reason = True, f"CPU 峰值 {cpu.get('max')}% 超过阈值"
        elif (mem.get("max") or 0) >= env_settings.memory_alert_percent:
            alert, reason = True, f"内存峰值 {mem.get('max')}% 超过阈值"
        elif (loss.get("max") or 0) >= env_settings.ping_loss_alert_percent:
            alert, reason = True, f"网络丢包峰值 {loss.get('max')}%"
        elif (latency.get("max") or 0) >= env_settings.ping_latency_alert_ms:
            alert, reason = True, f"Ping 延迟峰值 {latency.get('max')}ms"
        else:
            for disk in disks:
                if (disk.get("free_gb") or 0) < env_settings.disk_free_alert_gb:
                    alert = True
                    reason = f"磁盘 {disk.get('mountpoint')} 剩余 {disk.get('free_gb')}GB"
                    break

        score = 90
        if alert:
            score = 45
        elif (cpu.get("avg") or 0) > 70 or (mem.get("avg") or 0) > 80:
            score = 70

        return {
            "summary": "；".join(parts) + "。",
            "alert": alert,
            "alert_reason": reason,
            "health_score": score,
            "source": "rules",
        }

    async def chat(
        self,
        user_message: str,
        status_context: dict[str, Any],
        *,
        use_model: bool = True,
    ) -> str:
        if not use_model:
            return self._chat_without_model(status_context)

        context_json = json.dumps(status_context, ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"当前系统状态：\n{context_json}\n\n用户问题：{user_message}",
            },
        ]
        return await self.llm.chat(
            messages,
            model=env_settings.llm_model,
            temperature=env_settings.llm_temperature,
        )

    def _chat_without_model(self, status_context: dict[str, Any]) -> str:
        snap = status_context.get("snapshot") or {}
        summary = status_context.get("llm_summary") or {}
        if summary.get("summary"):
            return str(summary["summary"])
        net = snap.get("network") or {}
        ping = net.get("ping") or {}
        return (
            f"CPU {snap.get('cpu_percent')}% · 内存 {snap.get('memory_percent')}% · "
            f"Ping {ping.get('latency_ms')}ms · 告警 {status_context.get('alert_active')}"
        )
