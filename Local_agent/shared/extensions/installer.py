"""扩展安装 / 卸载。"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from shared.extensions.contract import (
    PACKAGE_SUFFIX,
    InstallResult,
    InstalledExtension,
    UninstallResult,
)
from shared.extensions.loader import apply_reload, get_host, unload_one
from shared.extensions.manifest import ManifestError, load_manifest
from shared.extensions.slots_dyn import unregister_extension_llm_slots
from shared.extensions.state import (
    extensions_root,
    is_bundled,
    load_installed_state,
    resolve_extension_path,
    save_installed_state,
)

logger = logging.getLogger(__name__)


class InstallError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _pip_install(specs: list[str]) -> None:
    if not specs:
        return
    cmd = [sys.executable, "-m", "pip", "install", *specs]
    logger.info("pip install: %s", " ".join(specs))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise InstallError(f"pip install 失败:\n{proc.stderr or proc.stdout}")


def _run_post_install(actions) -> None:
    for action in actions:
        if action.action == "playwright_install":
            browsers = list(action.browsers) or ["chromium"]
            cmd = [sys.executable, "-m", "playwright", "install", *browsers]
            logger.info("post_install: %s", " ".join(cmd))
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise InstallError(f"playwright install 失败:\n{proc.stderr or proc.stdout}")
        else:
            raise InstallError(f"未知 post_install: {action.action}")


def _extract_hamod(src: Path, dest_parent: Path, expected_id: str | None = None) -> Path:
    """解压到 dest_parent/<id>/，返回该目录。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(tmp_path)
        # 定位 manifest
        manifests = list(tmp_path.rglob("manifest.yaml"))
        if not manifests:
            raise InstallError("包内缺少 manifest.yaml")
        # 取路径最短者
        manifests.sort(key=lambda p: len(p.parts))
        manifest_path = manifests[0]
        package_root = manifest_path.parent
        manifest = load_manifest(manifest_path)
        if expected_id and manifest.id != expected_id:
            raise InstallError(f"包 id={manifest.id} 与期望 {expected_id} 不符")
        target = dest_parent / manifest.id
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(package_root, target)
        return target


def _collect_pip_specs(root: Path, packages: tuple[str, ...]) -> list[str]:
    specs = list(packages)
    req = root / "requirements.txt"
    if req.is_file():
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            specs.append(line)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for s in specs:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def register_bundled(
    base_dir: Path,
    *,
    module_id: str,
    rel_path: str,
) -> None:
    """把仓库内置扩展写入 installed.json（不复制、不 pip）。"""
    root = resolve_extension_path(base_dir, rel_path)
    manifest = load_manifest(root)
    if manifest.id != module_id:
        raise InstallError(f"bundled id mismatch: {manifest.id} vs {module_id}")
    state = load_installed_state(base_dir)
    state.extensions[module_id] = InstalledExtension(
        version=manifest.version,
        enabled=True,
        installed_at=_now_iso(),
        path=rel_path.replace("\\", "/"),
        status="ready",
        pip_specs=tuple(manifest.requires.packages),
    )
    save_installed_state(base_dir, state, bundled_ids={module_id})


def ensure_default_bundled(base_dir: Path) -> None:
    """首次启动：若无 crawler 安装记录，则注册内置 modules/crawler。"""
    state = load_installed_state(base_dir)
    if "crawler" in state.extensions:
        return
    bundled = base_dir / "modules" / "crawler" / "manifest.yaml"
    if bundled.is_file():
        register_bundled(base_dir, module_id="crawler", rel_path="modules/crawler")
        logger.info("seeded bundled extension: crawler")


async def install_hamod(
    source: Path | str | bytes,
    *,
    base_dir: Path | None = None,
    apply: bool = True,
) -> InstallResult:
    host_base = base_dir
    if host_base is None:
        try:
            host_base = get_host().base_dir
        except RuntimeError:
            from app.config import settings

            host_base = settings.base_dir

    ext_root = extensions_root(host_base)
    ext_root.mkdir(parents=True, exist_ok=True)

    tmp_zip: Path | None = None
    try:
        if isinstance(source, (bytes, bytearray)):
            tmp_zip = Path(tempfile.mkstemp(suffix=PACKAGE_SUFFIX)[1])
            tmp_zip.write_bytes(source)
            src_path = tmp_zip
        else:
            src_path = Path(source)
            if not src_path.is_file():
                raise InstallError(f"找不到安装包: {src_path}")

        target = _extract_hamod(src_path, ext_root)
        manifest = load_manifest(target)
        pip_specs = _collect_pip_specs(target, manifest.requires.packages)
        try:
            _pip_install(pip_specs)
            _run_post_install(manifest.post_install)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

        state = load_installed_state(host_base)
        state.extensions[manifest.id] = InstalledExtension(
            version=manifest.version,
            enabled=True,
            installed_at=_now_iso(),
            path=f"extensions/{manifest.id}",
            status="ready",
            pip_specs=tuple(pip_specs),
        )
        save_installed_state(host_base, state)

        apply_mode = "restart_required"
        if apply:
            try:
                get_host()
                await apply_reload()
                apply_mode = "reloaded"
            except RuntimeError:
                apply_mode = "restart_required"

        return InstallResult(
            module_id=manifest.id,
            version=manifest.version,
            apply=apply_mode,  # type: ignore[arg-type]
            message="installed",
        )
    finally:
        if tmp_zip is not None:
            tmp_zip.unlink(missing_ok=True)


async def uninstall(
    module_id: str,
    *,
    base_dir: Path | None = None,
    purge_data: bool = False,
    purge_deps: bool = False,
    purge_slots: bool = True,
    apply: bool = True,
) -> UninstallResult:
    host_base = base_dir
    if host_base is None:
        try:
            host_base = get_host().base_dir
        except RuntimeError:
            from app.config import settings

            host_base = settings.base_dir

    state = load_installed_state(host_base)
    meta = state.extensions.get(module_id)
    if not meta:
        raise InstallError(f"未安装: {module_id}")

    bundled = is_bundled(host_base, module_id)

    try:
        await unload_one(module_id, purge_slots=purge_slots)
    except RuntimeError:
        if purge_slots:
            unregister_extension_llm_slots(module_id)
    except Exception:
        logger.exception("unload before uninstall failed")

    root = resolve_extension_path(host_base, meta.path)
    if not bundled and root.is_dir():
        try:
            root.resolve().relative_to(extensions_root(host_base).resolve())
        except ValueError:
            pass
        else:
            shutil.rmtree(root, ignore_errors=True)

    if purge_deps and meta.pip_specs:
        cmd = [sys.executable, "-m", "pip", "uninstall", "-y", *meta.pip_specs]
        logger.info("pip uninstall: %s", " ".join(meta.pip_specs))
        subprocess.run(cmd, capture_output=True, text=True)

    if purge_data:
        data_dir = host_base / "data" / module_id
        if data_dir.is_dir():
            shutil.rmtree(data_dir, ignore_errors=True)

    del state.extensions[module_id]
    save_installed_state(host_base, state)

    apply_mode = "restart_required"
    if apply:
        try:
            get_host()
            await apply_reload()
            apply_mode = "reloaded"
        except RuntimeError:
            apply_mode = "restart_required"

    return UninstallResult(module_id=module_id, apply=apply_mode, message="uninstalled")  # type: ignore[arg-type]


def list_extensions_public(base_dir: Path | None = None) -> list[dict]:
    from shared.extensions.registry import get_loaded

    if base_dir is None:
        from app.config import settings

        base_dir = settings.base_dir
    state = load_installed_state(base_dir)
    out: list[dict] = []
    for mid, meta in state.extensions.items():
        loaded = get_loaded(mid)
        manifest = loaded.manifest if loaded else None
        if manifest is None and meta.path:
            try:
                manifest = load_manifest(resolve_extension_path(base_dir, meta.path))
            except ManifestError:
                manifest = None
        item = {
            "id": mid,
            "version": meta.version,
            "enabled": meta.enabled,
            "status": meta.status,
            "error": meta.error,
            "bundled": is_bundled(base_dir, mid),
            "loaded": loaded is not None,
            "path": meta.path,
        }
        if manifest:
            item.update(
                {
                    "name": manifest.name,
                    "description": manifest.description,
                    "ui": {
                        "label": manifest.ui.label,
                        "icon": manifest.ui.icon,
                        "default_msg_types": list(manifest.ui.default_msg_types),
                        "workspace": manifest.ui.workspace,
                    },
                    "llm_slots": [
                        {"key": s.key, "label": s.label, "capability": s.capability}
                        for s in manifest.llm_slots
                    ],
                    "tools": [t.name for t in (loaded.tools if loaded else [])],
                }
            )
        out.append(item)
    return out
