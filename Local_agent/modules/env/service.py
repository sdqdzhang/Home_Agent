from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.env import DEFAULT_MSG_TYPE, MODULE_ALIASES, CAMERA_MSG_TYPE, SCREENSHOT_MSG_TYPE
from modules.env.aggregator import aggregate_samples
from modules.env.camera import capture_camera_async
from modules.env.collectors import collect_snapshot
from modules.env.config import env_settings
from modules.env.model import EnvAssistant
from modules.env.screenshot import capture_desktop_async

logger = logging.getLogger(__name__)


def _metric_max(value: Any) -> float | None:
    """聚合窗口为 {avg,max,min}，单次快照为标量。"""
    if isinstance(value, dict):
        return value.get("max")
    if isinstance(value, (int, float)):
        return float(value)
    return None


class EnvService:
    """环境感知服务：20s 采集、10min 压缩汇报、按需截图、供主 Agent 读取的状态接口。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        env_settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.server = server_client
        self.assistant = EnvAssistant()
        self.use_model = True

        self._samples: list[dict[str, Any]] = []
        self._prev_net_counters = None
        self._prev_net_time: float | None = None
        self._latest_snapshot: dict[str, Any] = {}
        self._latest_aggregated: dict[str, Any] = {}
        self._llm_summary: dict[str, Any] = {}
        self._alert_active = False
        self._alert_reason = ""

        self._collect_task: asyncio.Task[None] | None = None
        self._summary_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def status_payload(self) -> dict[str, Any]:
        return {
            "snapshot": self._latest_snapshot,
            "aggregated": self._latest_aggregated,
            "llm_summary": self._llm_summary,
            "alert_active": self._alert_active,
            "alert_reason": self._alert_reason,
            "updated_at": self._latest_snapshot.get("timestamp_iso"),
        }

    async def start(self, *, use_model: bool = True) -> None:
        self.use_model = use_model
        if self._collect_task and not self._collect_task.done():
            return
        self._collect_task = asyncio.create_task(self._collect_loop())
        self._summary_task = asyncio.create_task(self._summary_loop())
        logger.info(
            "EnvService started (collect=%ss, summary=%ss, model=%s)",
            env_settings.collect_interval_seconds,
            env_settings.summary_interval_seconds,
            use_model,
        )

    async def stop(self) -> None:
        for task in (self._collect_task, self._summary_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._collect_task = None
        self._summary_task = None

    async def collect_once(self, *, push: bool = False) -> dict[str, Any]:
        async with self._lock:
            snapshot, counters, net_time = await asyncio.to_thread(
                collect_snapshot,
                prev_net_counters=self._prev_net_counters,
                prev_net_time=self._prev_net_time,
            )
            self._prev_net_counters = counters
            self._prev_net_time = net_time
            self._latest_snapshot = snapshot
            self._samples.append(snapshot)
            max_samples = max(1, env_settings.summary_interval_seconds // env_settings.collect_interval_seconds)
            if len(self._samples) > max_samples:
                self._samples = self._samples[-max_samples:]
            self._latest_aggregated = aggregate_samples(
                self._samples,
                interval_seconds=env_settings.collect_interval_seconds,
            )
            rule_alert, rule_reason = self._evaluate_rules_snapshot(snapshot)
            self._alert_active = rule_alert
            self._alert_reason = rule_reason if rule_alert else ""
            push_result = None
            if push:
                push_result = await self._push_status(report_type="snapshot", snapshot=snapshot)
            return {"snapshot": snapshot, "push": push_result}

    async def run_summary(self, *, push: bool = True, use_model: bool | None = None) -> dict[str, Any]:
        async with self._lock:
            aggregated = aggregate_samples(
                self._samples,
                interval_seconds=env_settings.collect_interval_seconds,
            )
            self._latest_aggregated = aggregated
            model_flag = self.use_model if use_model is None else use_model
            summary = await self.assistant.summarize(aggregated, use_model=model_flag)
            summary["generated_at"] = datetime.now(tz=timezone.utc).isoformat()
            self._llm_summary = summary

            alert = bool(summary.get("alert")) or self._evaluate_rules_window(self._latest_snapshot, aggregated)[0]
            reason = str(summary.get("alert_reason") or "") or self._evaluate_rules_window(self._latest_snapshot, aggregated)[1]
            # 周期总结可触发告警，但下次快照推送会按当前指标重新评估并清除
            if alert:
                self._alert_active = True
                self._alert_reason = reason
            if push:
                await self._push_status(report_type="summary", aggregated=aggregated, llm_summary=summary)
            self._samples.clear()
            return {"aggregated": aggregated, "llm_summary": summary, "alert_active": self._alert_active}

    async def chat(self, user_message: str, *, use_model: bool | None = None) -> str:
        await self.collect_once(push=False)
        model_flag = self.use_model if use_model is None else use_model
        reply = await self.assistant.chat(user_message, self.status_payload, use_model=model_flag)
        if self.server:
            await self.server.send_message(
                msg_type="text",
                message={"text": reply, "role": "agent"},
            )
        return reply

    async def take_screenshot(self, *, push: bool = True) -> dict[str, Any]:
        try:
            shot = await capture_desktop_async()
        except Exception as exc:
            logger.exception("Desktop screenshot failed")
            err = {
                "ok": False,
                "error": str(exc),
                "capture_type": "desktop",
                "text": f"截图失败：{exc}",
                "status": "error",
            }
            if push and self.server:
                await self.server.send_message(msg_type=SCREENSHOT_MSG_TYPE, message=err)
            return err
        if push and self.server:
            await self.server.send_message(
                msg_type=SCREENSHOT_MSG_TYPE,
                message={
                    "ok": True,
                    "text": "远程桌面截图",
                    "capture_type": "desktop",
                    "saved_path": shot.get("saved_path"),
                    **shot,
                },
            )
        return {"ok": True, **shot}

    async def take_camera_photo(self, *, push: bool = True) -> dict[str, Any]:
        try:
            photo = await capture_camera_async()
        except Exception as exc:
            logger.exception("Camera capture failed")
            err = {
                "ok": False,
                "error": str(exc),
                "capture_type": "camera",
                "text": f"摄像头拍照失败：{exc}",
                "status": "error",
            }
            if push and self.server:
                await self.server.send_message(msg_type=CAMERA_MSG_TYPE, message=err)
            return err
        if push and self.server:
            await self.server.send_message(
                msg_type=CAMERA_MSG_TYPE,
                message={
                    "ok": True,
                    "text": "摄像头拍照",
                    "capture_type": "camera",
                    "saved_path": photo.get("saved_path"),
                    **photo,
                },
            )
        return {"ok": True, **photo}

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES:
            return

        message = data.get("message") or {}
        payload = message.get("payload") or {}
        action = payload.get("action")
        msg_type = data.get("msg_type", "text")

        if action == "screenshot":
            await self.take_screenshot(push=True)
            return

        if action == "camera":
            await self.take_camera_photo(push=True)
            return

        if msg_type == "text":
            text = (message.get("text") or "").strip()
            if text:
                await self.chat(text)

    async def _collect_loop(self) -> None:
        while True:
            try:
                await self.collect_once(push=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Env collect failed")
            await asyncio.sleep(env_settings.collect_interval_seconds)

    async def _summary_loop(self) -> None:
        await asyncio.sleep(env_settings.summary_interval_seconds)
        while True:
            try:
                await self.run_summary(push=True)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Env summary failed")
            await asyncio.sleep(env_settings.summary_interval_seconds)

    def _evaluate_rules_snapshot(self, snapshot: dict[str, Any]) -> tuple[bool, str]:
        """单次快照告警：仅看当前采集值，恢复后立即清除。"""
        cpu = snapshot.get("cpu_percent") or 0
        mem = snapshot.get("memory_percent") or 0
        if cpu >= env_settings.cpu_alert_percent:
            return True, f"CPU 占用过高（{cpu}%）"
        if mem >= env_settings.memory_alert_percent:
            return True, f"内存占用过高（{mem}%）"
        ping = (snapshot.get("network") or {}).get("ping") or {}
        if not ping.get("skipped"):
            loss = ping.get("packet_loss_percent")
            latency = ping.get("latency_ms")
            if loss is not None and loss >= env_settings.ping_loss_alert_percent:
                return True, f"网络丢包过高（{loss}%）"
            if latency is not None and latency >= env_settings.ping_latency_alert_ms:
                return True, f"网络延迟过高（{latency}ms）"
        for disk in snapshot.get("disks") or []:
            if (disk.get("free_gb") or 0) < env_settings.disk_free_alert_gb:
                return True, f"磁盘 {disk.get('mountpoint')} 空间不足（剩余 {disk.get('free_gb')}GB）"
        return False, ""

    def _evaluate_rules_window(
        self,
        snapshot: dict[str, Any],
        aggregated: dict[str, Any],
    ) -> tuple[bool, str]:
        """窗口期告警：用于周期总结，看窗口内峰值。"""
        cpu_max = (aggregated.get("cpu_percent") or {}).get("max") or snapshot.get("cpu_percent") or 0
        mem_max = (aggregated.get("memory_percent") or {}).get("max") or snapshot.get("memory_percent") or 0
        ping = (aggregated.get("network") or {}).get("ping") or (snapshot.get("network") or {}).get("ping") or {}
        loss_max = _metric_max(ping.get("packet_loss_percent"))
        latency_max = _metric_max(ping.get("latency_ms"))

        if cpu_max >= env_settings.cpu_alert_percent:
            return True, f"CPU 占用过高（{cpu_max}%）"
        if mem_max >= env_settings.memory_alert_percent:
            return True, f"内存占用过高（{mem_max}%）"
        if (loss_max is not None) and loss_max >= env_settings.ping_loss_alert_percent:
            return True, f"网络丢包过高（{loss_max}%）"
        if latency_max is not None and latency_max >= env_settings.ping_latency_alert_ms:
            return True, f"网络延迟过高（{latency_max}ms）"
        for disk in snapshot.get("disks") or []:
            if (disk.get("free_gb") or 0) < env_settings.disk_free_alert_gb:
                return True, f"磁盘 {disk.get('mountpoint')} 空间不足（剩余 {disk.get('free_gb')}GB）"
        return False, ""

    def _evaluate_rules(
        self,
        snapshot: dict[str, Any],
        aggregated: dict[str, Any],
    ) -> tuple[bool, str]:
        return self._evaluate_rules_window(snapshot, aggregated)

    async def _set_alert(self, active: bool, reason: str, *, push: bool) -> dict[str, Any] | None:
        changed = active != self._alert_active or (active and reason != self._alert_reason)
        self._alert_active = active
        self._alert_reason = reason if active else ""
        if push and changed:
            return await self._push_status(
                report_type="alert" if active else "alert_cleared",
                alert=active,
                alert_reason=self._alert_reason,
            )
        return None

    async def _push_status(
        self,
        *,
        report_type: str,
        snapshot: dict[str, Any] | None = None,
        aggregated: dict[str, Any] | None = None,
        llm_summary: dict[str, Any] | None = None,
        alert: bool | None = None,
        alert_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.server:
            raise RuntimeError("未配置 Server Center 客户端，无法推送")
        snap = snapshot or self._latest_snapshot
        agg = aggregated or self._latest_aggregated
        summary = llm_summary or self._llm_summary
        message: dict[str, Any] = {
            "report_type": report_type,
            "text": self._format_status_text(snapshot=snap, aggregated=agg, llm_summary=summary),
            "alert": self._alert_active if alert is None else alert,
            "alert_reason": self._alert_reason if alert_reason is None else alert_reason,
            "snapshot": {
                "cpu_percent": snap.get("cpu_percent"),
                "memory_percent": snap.get("memory_percent"),
                "memory_used_gb": snap.get("memory_used_gb"),
                "memory_total_gb": snap.get("memory_total_gb"),
                "disks": snap.get("disks"),
                "network": snap.get("network"),
                "top_processes": snap.get("top_processes"),
                "timestamp_iso": snap.get("timestamp_iso"),
            },
        }
        if report_type == "summary" and agg:
            message["aggregated"] = agg
            message["llm_summary"] = summary
        return await self.server.send_message(msg_type=DEFAULT_MSG_TYPE, message=message)

    def _format_status_text(
        self,
        *,
        snapshot: dict[str, Any] | None = None,
        aggregated: dict[str, Any] | None = None,
        llm_summary: dict[str, Any] | None = None,
    ) -> str:
        snap = snapshot or self._latest_snapshot
        summary = llm_summary or self._llm_summary
        if summary.get("summary"):
            return str(summary["summary"])
        net = snap.get("network") or {}
        ping = net.get("ping") or {}
        proxy = "代理开" if net.get("proxy_enabled") else "代理关"
        vpn = "VPN开" if net.get("vpn_active") else "VPN关"
        ping_text = "Ping 未测"
        if not ping.get("skipped") and ping.get("latency_ms") is not None:
            ping_text = f"Ping {ping.get('latency_ms')}ms 丢包{ping.get('packet_loss_percent')}%"
        return (
            f"CPU {snap.get('cpu_percent')}% · 内存 {snap.get('memory_percent')}% "
            f"({snap.get('memory_used_gb')}/{snap.get('memory_total_gb')}GB) · "
            f"↑{net.get('upload_mbps')} ↓{net.get('download_mbps')} MB/s · "
            f"{ping_text} · {proxy}/{vpn}"
        )
