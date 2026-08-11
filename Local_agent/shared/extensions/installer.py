"""扩展安装 / 卸载。"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
from shared.extensions.pack import PackError, pack_extension, rewrite_tree_in_place, tree_has_legacy_imports
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


def _safe_unlink(path: Path, *, retries: int = 8, delay: float = 0.05) -> None:
    for i in range(retries):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if i + 1 >= retries:
                logger.warning("could not delete temp file %s (locked)", path)
                return
            time.sleep(delay * (i + 1))


def _pip_install(specs: list[str], *, timeout_sec: int = 180) -> None:
    """安装缺失依赖；已满足的跳过。超时则失败（避免前端一直转圈）。"""
    pending = [s for s in specs if not _pip_req_satisfied(s)]
    if not pending:
        logger.info("pip: all requirements already satisfied (%s)", specs)
        return
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        *pending,
    ]
    logger.info("pip install: %s", " ".join(pending))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        raise InstallError(f"pip install 超时（>{timeout_sec}s）: {' '.join(pending)}") from exc
    if proc.returncode != 0:
        raise InstallError(f"pip install 失败:\n{proc.stderr or proc.stdout}")


def _pip_req_satisfied(spec: str) -> bool:
    """粗测：纯包名能否 import；带版本符的仍走 pip（由 pip 自己判断）。"""
    name = spec.strip()
    if not name or any(op in name for op in "<>!=[~"):
        return False
    # PEP 508 extras: pkg[extra]
    dist = name.split("[", 1)[0].strip()
    mod = dist.replace("-", "_")
    try:
        __import__(mod)
        return True
    except Exception:
        # 常见发行名与模块名不一致时让 pip 处理
        try:
            import importlib.metadata as md

            md.version(dist)
            return True
        except Exception:
            return False


def _run_post_install(actions, *, timeout_sec: int = 300) -> None:
    for action in actions:
        if action.action == "playwright_install":
            browsers = list(action.browsers) or ["chromium"]
            cmd = [sys.executable, "-m", "playwright", "install", *browsers]
            logger.info("post_install: %s", " ".join(cmd))
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            except subprocess.TimeoutExpired as exc:
                raise InstallError(f"playwright install 超时（>{timeout_sec}s）") from exc
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


def _ensure_self_contained(root: Path, module_id: str) -> None:
    """安装到 extensions/ 的代码必须自包含，并规避与标准库同名的包冲突。"""
    from shared.extensions.pack import fix_stdlib_shadows

    if tree_has_legacy_imports(root, module_id):
        if rewrite_tree_in_place(root, module_id=module_id):
            logger.info("rewrote legacy imports for self-contained extension %s", module_id)
    elif fix_stdlib_shadows(root):
        logger.info("fixed stdlib-shadowed packages for extension %s", module_id)


def register_bundled(
    base_dir: Path,
    *,
    module_id: str,
    rel_path: str,
) -> str:
    """把仓库源码打包并物化到 extensions/<id>/（可干净卸载）。返回 module_id。"""
    src = resolve_extension_path(base_dir, rel_path)
    if not src.is_dir():
        raise InstallError(f"找不到源目录: {src}")
    return materialize_from_source(src, base_dir, new_id=module_id)


def materialize_from_source(
    src: Path,
    base_dir: Path,
    *,
    new_id: str | None = None,
    new_name: str | None = None,
) -> str:
    """pack → 解压到 extensions/ → 写 installed.json。同步，不 apply。"""
    ext_root = extensions_root(base_dir)
    ext_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hamod_mat_") as td:
        try:
            hamod = pack_extension(src, output_dir=td, new_id=new_id, new_name=new_name)
        except PackError as exc:
            raise InstallError(str(exc)) from exc
        target = _extract_hamod(hamod, ext_root)
        manifest = load_manifest(target)
        _ensure_self_contained(target, manifest.id)
        pip_specs = _collect_pip_specs(target, manifest.requires.packages)
        # 物化时不强制 pip（依赖已在开发环境）；正式 install_hamod 会 pip
        state = load_installed_state(base_dir)
        state.extensions[manifest.id] = InstalledExtension(
            version=manifest.version,
            enabled=True,
            installed_at=_now_iso(),
            path=f"extensions/{manifest.id}",
            status="ready",
            pip_specs=tuple(pip_specs),
        )
        save_installed_state(base_dir, state)
        logger.info("materialized extension %s -> %s", manifest.id, target)
        return manifest.id


def ensure_default_bundled(base_dir: Path) -> None:
    """保留兼容入口；扩展须通过 .hamod 安装，不再从 modules/ 自动物化。"""
    _ = base_dir


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
    tmp_fd: int | None = None
    try:
        if isinstance(source, (bytes, bytearray)):
            # mkstemp 必须关闭 fd，否则 Windows 上 finally unlink 会 WinError 32
            tmp_fd, tmp_name = tempfile.mkstemp(suffix=PACKAGE_SUFFIX)
            os.close(tmp_fd)
            tmp_fd = None
            tmp_zip = Path(tmp_name)
            tmp_zip.write_bytes(source)
            src_path = tmp_zip
        else:
            src_path = Path(source)
            if not src_path.is_file():
                raise InstallError(f"找不到安装包: {src_path}")

        target = _extract_hamod(src_path, ext_root)
        manifest = load_manifest(target)
        _ensure_self_contained(target, manifest.id)
        pip_specs = _collect_pip_specs(target, manifest.requires.packages)
        try:
            _pip_install(pip_specs)
            _run_post_install(manifest.post_install)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise

        state = load_installed_state(host_base)
        # 升级：覆盖同 id
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
        apply_error = ""
        if apply:
            try:
                get_host()
                await apply_reload()
                apply_mode = "reloaded"
            except RuntimeError:
                apply_mode = "restart_required"
            except Exception as exc:
                logger.exception("apply after install failed")
                apply_mode = "restart_required"
                apply_error = str(exc)
                # 保持已写入的 installed.json，下次启动再 load
                state = load_installed_state(host_base)
                if manifest.id in state.extensions:
                    state.extensions[manifest.id].status = "error"
                    state.extensions[manifest.id].error = apply_error[:500]
                    save_installed_state(host_base, state)

        msg = "installed"
        if apply_error:
            msg = f"installed but apply failed: {apply_error[:200]}; restart Local Agent"

        return InstallResult(
            module_id=manifest.id,
            version=manifest.version,
            apply=apply_mode,  # type: ignore[arg-type]
            message=msg,
        )
    finally:
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except Exception:
                pass
        if tmp_zip is not None:
            _safe_unlink(tmp_zip)


async def uninstall(
    module_id: str,
    *,
    base_dir: Path | None = None,
    purge_data: bool = False,
    purge_deps: bool = False,
    purge_slots: bool = True,
    purge_code: bool = True,
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
    root = resolve_extension_path(host_base, meta.path)
    rel = str(meta.path).replace("\\", "/")

    try:
        await unload_one(module_id, purge_slots=purge_slots)
    except RuntimeError:
        if purge_slots:
            unregister_extension_llm_slots(module_id)
    except Exception:
        logger.exception("unload before uninstall failed")

    deleted_code = False
    if rel.startswith("modules/"):
        # 历史误登记：只注销，提示改用 extensions 安装
        logger.warning("uninstall %s: path is %s — skip deleting modules/; unregister only", module_id, rel)
    else:
        deleted_code = _delete_extension_code(
            host_base,
            root,
            bundled=bundled,
            purge_code=purge_code,
        )

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

    msg = "uninstalled"
    if deleted_code:
        msg += "; code removed from extensions/"
    elif rel.startswith("modules/"):
        msg += "; modules/ source kept (legacy path; reinstall via pack for clean uninstall)"
    return UninstallResult(module_id=module_id, apply=apply_mode, message=msg)  # type: ignore[arg-type]


def _delete_extension_code(
    host_base: Path,
    root: Path,
    *,
    bundled: bool,
    purge_code: bool,
) -> bool:
    """删除 extensions/<id>/ 已安装副本（卸载默认必删，才能清干净 / 支持升级重装）。

    永不删除 modules/ 或 extension_packages/ 开发源码树。
    """
    _ = bundled
    if not purge_code:
        return False
    if not root.is_dir():
        return False
    base = host_base.resolve()
    target = root.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise InstallError(f"拒绝删除 Local_agent 外路径: {target}") from exc

    for protected_name in ("modules", "extension_packages"):
        protected = (host_base / protected_name).resolve()
        try:
            target.relative_to(protected)
            raise InstallError(
                f"拒绝删除 {protected_name}/ 开发树: {target}。"
                "请先 pack 安装到 extensions/，再卸载；或手动保留源码。"
            )
        except ValueError:
            pass

    ext_root = extensions_root(host_base).resolve()
    try:
        target.relative_to(ext_root)
    except ValueError as exc:
        raise InstallError(f"只能删除 extensions/ 下的安装副本: {target}") from exc

    shutil.rmtree(target, ignore_errors=False)
    # 兜底：残留空壳也清掉
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    return not target.exists()


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
                    "has_settings": bool(manifest.settings),
                    "settings_count": len(manifest.settings),
                    "tools": [t.name for t in (loaded.tools if loaded else [])],
                }
            )
        out.append(item)
    return out
