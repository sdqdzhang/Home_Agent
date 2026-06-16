from __future__ import annotations

import platform
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

import psutil

from modules.env.config import env_settings

_VPN_KEYWORDS = (
    "vpn",
    "wireguard",
    "nordlynx",
    "tap",
    "tun",
    "wintun",
    "openvpn",
    "zerotier",
    "tailscale",
    "ppp",
)


def _ping_skipped(target: str, *, reason: str, replies: int = 0) -> dict[str, Any]:
    return {
        "target": target,
        "latency_ms": None,
        "packet_loss_percent": None,
        "reachable": None,
        "skipped": True,
        "skip_reason": reason,
        "replies": replies,
    }


def _ping_stats(target: str) -> dict[str, Any]:
    """Ping 公网目标；有效回复不足 ping_min_replies 时不报丢包率（避免 0%/100% 乱跳）。"""
    count = env_settings.ping_count
    min_replies = env_settings.ping_min_replies
    system = platform.system().lower()
    try:
        if system == "windows":
            proc = subprocess.run(
                ["ping", "-n", str(count), "-w", str(int(env_settings.ping_timeout_seconds * 1000)), target],
                capture_output=True,
                text=True,
                timeout=env_settings.ping_timeout_seconds * count + 5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            latencies: list[float] = []
            for match in re.finditer(r"(?:time|时间)[=<](\d+(?:\.\d+)?)\s*ms", output, re.I):
                latencies.append(float(match.group(1)))
        else:
            proc = subprocess.run(
                ["ping", "-c", str(count), "-W", str(int(env_settings.ping_timeout_seconds)), target],
                capture_output=True,
                text=True,
                timeout=env_settings.ping_timeout_seconds * count + 5,
            )
            output = (proc.stdout or "") + (proc.stderr or "")
            latencies = [float(x) for x in re.findall(r"time[=<](\d+(?:\.\d+)?)\s*ms", output, re.I)]

        if len(latencies) < min_replies:
            return _ping_skipped(target, reason="insufficient_replies", replies=len(latencies))

        loss: float | None = None
        loss_match = re.search(
            r"(\d+(?:\.\d+)?)%\s*(?:loss|packet loss)|丢失\s*=\s*(\d+(?:\.\d+)?)%",
            output,
            re.I,
        )
        if loss_match:
            loss = float(loss_match.group(1) or loss_match.group(2))
        else:
            loss = round((count - len(latencies)) / count * 100, 2)

        latency = round(sum(latencies) / len(latencies), 2)
        return {
            "target": target,
            "latency_ms": latency,
            "packet_loss_percent": round(loss, 2),
            "reachable": loss < 100,
            "skipped": False,
            "replies": len(latencies),
        }
    except Exception as exc:
        return _ping_skipped(target, reason=str(exc))


def _proxy_enabled() -> bool:
    system = platform.system().lower()
    if system == "windows":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            ) as key:
                enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
                return bool(enabled)
        except OSError:
            return False
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        if __import__("os").environ.get(var):
            return True
    return False


def _vpn_active() -> bool:
    try:
        stats = psutil.net_if_stats()
        for name, info in stats.items():
            lowered = name.lower()
            if not info.isup:
                continue
            if any(kw in lowered for kw in _VPN_KEYWORDS):
                return True
    except Exception:
        pass
    return False


def _disk_info() -> list[dict[str, Any]]:
    disks: list[dict[str, Any]] = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype and "cdrom" in part.opts.lower():
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        disks.append(
            {
                "device": part.device,
                "mountpoint": part.mountpoint,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent": round(usage.percent, 2),
            }
        )
    return disks


def _top_processes(limit: int = 5) -> list[dict[str, Any]]:
    procs: list[dict[str, Any]] = []
    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = proc.info
            name = (info.get("name") or "unknown").lower()
            pid = info.get("pid")
            if pid in (0, None) or name in ("system idle process", "idle"):
                continue
            procs.append(
                {
                    "pid": pid,
                    "name": info.get("name") or "unknown",
                    "cpu_percent": round(float(info.get("cpu_percent") or 0), 2),
                    "memory_percent": round(float(info.get("memory_percent") or 0), 2),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    procs.sort(key=lambda p: (p["cpu_percent"] + p["memory_percent"]), reverse=True)
    return procs[:limit]


def _network_rates(
    prev_counters: Any | None,
    prev_time: float | None,
) -> tuple[dict[str, float], Any, float]:
    counters = psutil.net_io_counters()
    now = time.time()
    upload_mbps = 0.0
    download_mbps = 0.0
    if prev_counters is not None and prev_time is not None:
        dt = max(now - prev_time, 0.001)
        upload_mbps = round((counters.bytes_sent - prev_counters.bytes_sent) * 8 / dt / 1_000_000, 3)
        download_mbps = round((counters.bytes_recv - prev_counters.bytes_recv) * 8 / dt / 1_000_000, 3)
    return (
        {"upload_mbps": upload_mbps, "download_mbps": download_mbps},
        counters,
        now,
    )


def collect_snapshot(
    *,
    prev_net_counters: Any | None = None,
    prev_net_time: float | None = None,
) -> tuple[dict[str, Any], Any, float]:
    """采集一次系统快照，返回 (snapshot, net_counters, net_time)。"""
    psutil.cpu_percent(interval=None)
    rates, counters, net_time = _network_rates(prev_net_counters, prev_net_time)
    ping = _ping_stats(env_settings.ping_target)
    memory = psutil.virtual_memory()
    snapshot = {
        "timestamp": int(net_time),
        "timestamp_iso": datetime.fromtimestamp(net_time, tz=timezone.utc).isoformat(),
        "cpu_percent": round(psutil.cpu_percent(interval=0.1), 2),
        "memory_percent": round(memory.percent, 2),
        "memory_used_gb": round(memory.used / (1024**3), 2),
        "memory_total_gb": round(memory.total / (1024**3), 2),
        "disks": _disk_info(),
        "network": {
            **rates,
            "ping": ping,
            "proxy_enabled": _proxy_enabled(),
            "vpn_active": _vpn_active(),
        },
        "top_processes": _top_processes(),
    }
    return snapshot, counters, net_time
