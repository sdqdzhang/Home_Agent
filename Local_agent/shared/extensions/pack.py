"""把扩展目录打成 .hamod（zip）。

支持 --id 改写为自包含包（可并行安装多份调试）。
布局见 docs/extension-packaging.md。
"""

from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
from pathlib import Path

import yaml

from shared.extensions.contract import PACKAGE_SUFFIX, validate_manifest_id
from shared.extensions.manifest import ManifestError, load_manifest

_SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    ".svn",
    ".hg",
    ".venv",
    "venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_SKIP_FILE_SUFFIXES = {".pyc", ".pyo", ".hamod"}
_SKIP_FILE_NAMES = {".ds_store", "thumbs.db"}

# 开发源码目录（打包时改写为 extensions/<id>/ 自包含导入）
_DEV_SOURCE_DIRS = frozenset({"modules", "extension_packages"})


class PackError(RuntimeError):
    pass


def _should_skip(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    for part in rel.parts:
        if part.startswith(".") and part not in (".", ".."):
            return True
        if part in _SKIP_DIR_NAMES:
            return True
    if path.is_file():
        name = path.name.lower()
        if name in _SKIP_FILE_NAMES:
            return True
        if path.suffix.lower() in _SKIP_FILE_SUFFIXES:
            return True
        if name.endswith(".example"):
            return True
    return False


def _safe_version_slug(version: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", version.strip())
    return slug or "0.0.0"


def _legacy_pkg_prefixes(module_id: str) -> tuple[str, ...]:
    return (f"modules.{module_id}", f"extension_packages.{module_id}")


def tree_has_legacy_imports(root: Path, module_id: str) -> bool:
    """安装树里是否仍含 modules.<id> / extension_packages.<id> 导入。"""
    needles = _legacy_pkg_prefixes(module_id)
    for path in root.rglob("*.py"):
        if _should_skip(path, root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if any(n in text for n in needles):
            return True
    return False


def _is_dev_source(source: Path) -> bool:
    return bool(_DEV_SOURCE_DIRS.intersection(source.resolve().parts))


# 包内子目录若与标准库同名，改写后会撞车；安装前映射到安全名
_STDLIB_SHADOW_MAP = {
    "logging": "crawl_logging",
}


def _safe_subpkg(sub: str) -> str:
    first, sep, rest = sub.partition(".")
    mapped = _STDLIB_SHADOW_MAP.get(first, first)
    return f"{mapped}{sep}{rest}" if sep else mapped


def _rewrite_python_source(text: str, *, old_id: str, new_id: str, old_pkg: str) -> str:
    """把 modules.<old_id> 导入改成包根相对导入；改写 MODULE_ID / 工具名。"""

    def _from_sub(m: re.Match[str]) -> str:
        return f"from {_safe_subpkg(m.group(1))} import"

    def _import_sub(m: re.Match[str]) -> str:
        return f"import {_safe_subpkg(m.group(1))}"

    # from modules.crawler.xxx import → from xxx import（logging → crawl_logging）
    text = re.sub(
        rf"from\s+{re.escape(old_pkg)}\.([a-zA-Z0-9_\.]+)\s+import",
        _from_sub,
        text,
    )
    # from modules.crawler import X → keep selective: MODULE_ID etc from local
    text = re.sub(
        rf"from\s+{re.escape(old_pkg)}\s+import\s+([^\n]+)",
        r"from __init__ import \1",
        text,
    )
    # import modules.crawler.xxx → import xxx
    text = re.sub(
        rf"import\s+{re.escape(old_pkg)}\.([a-zA-Z0-9_\.]+)",
        _import_sub,
        text,
    )

    # 兜底：regex 未覆盖的残留
    text = text.replace(f"from {old_pkg}.service import", "from service import")
    text = text.replace(f"from {old_pkg}.main_tools import", "from main_tools import")
    text = text.replace(f"from {old_pkg}.logging import", "from crawl_logging import")
    text = text.replace(f"from {old_pkg}.crawl_logging import", "from crawl_logging import")

    if old_id != new_id:
        text = re.sub(
            rf'MODULE_ID\s*=\s*["\']{re.escape(old_id)}["\']',
            f'MODULE_ID = "{new_id}"',
            text,
        )
        # ToolSpec name / module_id
        text = text.replace(f'name="crawler_fetch"', f'name="{new_id}_fetch"')
        text = text.replace(f'name="crawler_fetch_batch"', f'name="{new_id}_fetch_batch"')
        text = text.replace(f'module_id="crawler"', f'module_id="{new_id}"')
        text = text.replace(f'module_id="{old_id}"', f'module_id="{new_id}"')
        text = text.replace(f'crawler.pipeline', f"{new_id}.pipeline")
        text = text.replace(f'crawler.chat', f"{new_id}.chat")
        # capability 里仍可能写死 crawler
        if old_id == "crawler":
            text = text.replace('crawler_fetch_batch', f"{new_id}_fetch_batch")
            text = text.replace('crawler_fetch', f"{new_id}_fetch")

    return text


def _fix_shadow_imports_in_text(text: str) -> str:
    """修旧包：from logging import JobLogger → crawl_logging（不动 import logging / logging.getLogger）。"""
    text = re.sub(
        r"from\s+logging\s+import\s+JobLogger\b",
        "from crawl_logging import JobLogger",
        text,
    )
    text = re.sub(
        r"from\s+logging\.(job_logger)\s+import",
        r"from crawl_logging.\1 import",
        text,
    )
    return text


def fix_stdlib_shadows(work: Path) -> bool:
    """旧 hamod 若含 logging/ 业务包，改名为 crawl_logging/ 并修正导入。"""
    changed = False
    for shadow, safe in _STDLIB_SHADOW_MAP.items():
        src = work / shadow
        dst = work / safe
        if not src.is_dir():
            continue
        if not (src / "__init__.py").is_file():
            continue
        if dst.exists():
            shutil.rmtree(src, ignore_errors=True)
        else:
            src.rename(dst)
        changed = True

    for path in work.rglob("*.py"):
        if _should_skip(path, work):
            continue
        raw = path.read_text(encoding="utf-8")
        new_text = _fix_shadow_imports_in_text(raw)
        if new_text != raw:
            path.write_text(new_text, encoding="utf-8")
            changed = True
    return changed


def rewrite_tree_in_place(work: Path, *, module_id: str, new_id: str | None = None) -> bool:
    """把扩展目录改写成自包含导入（供 install / 修复旧安装副本）。"""
    pkg_id = new_id or module_id
    changed = False
    for path in work.rglob("*.py"):
        if _should_skip(path, work):
            continue
        raw = path.read_text(encoding="utf-8")
        new_text = raw
        for old_pkg in _legacy_pkg_prefixes(module_id):
            new_text = _rewrite_python_source(new_text, old_id=module_id, new_id=pkg_id, old_pkg=old_pkg)
        new_text = _fix_shadow_imports_in_text(new_text)
        if new_text != raw:
            path.write_text(new_text, encoding="utf-8")
            changed = True
    if fix_stdlib_shadows(work):
        changed = True
    return changed


def _rewrite_manifest_dict(
    data: dict,
    *,
    new_id: str,
    new_name: str | None,
    old_id: str,
) -> dict:
    data = dict(data)
    data["id"] = new_id
    if new_name:
        data["name"] = new_name
    aliases = list(data.get("aliases") or [])
    aliases = [new_id if a == old_id else a for a in aliases]
    if new_id not in aliases:
        aliases.insert(0, new_id)
    if new_name and new_name not in aliases:
        aliases.append(new_name)
    data["aliases"] = aliases

    slots = []
    for slot in data.get("llm_slots") or []:
        s = dict(slot)
        key = str(s.get("key") or "")
        if key.startswith(f"{old_id}."):
            s["key"] = f"{new_id}." + key.split(".", 1)[1]
        elif key.startswith("crawler.") and old_id == "crawler":
            s["key"] = f"{new_id}." + key.split(".", 1)[1]
        slots.append(s)
    if slots:
        data["llm_slots"] = slots

    ui = dict(data.get("ui") or {})
    if new_name and not ui.get("label"):
        ui["label"] = new_name
    elif new_name and old_id == "crawler":
        ui["label"] = new_name
    data["ui"] = ui
    return data


def _prepare_pack_tree(
    source: Path,
    *,
    new_id: str | None,
    new_name: str | None,
) -> tuple[Path, str, tempfile.TemporaryDirectory[str] | None]:
    """返回 (工作目录, package_id, tmp_ctx或None)。工作目录需在打包后由调用方保持 tmp 存活。"""
    manifest = load_manifest(source)
    old_id = manifest.id
    pkg_id = new_id or old_id
    if not validate_manifest_id(pkg_id):
        raise PackError(f"非法 id: {pkg_id}")

    # 开发树或仍含 modules.<id> 导入 → 必须改写成自包含（extensions/<id>/ 独立运行）
    need_rewrite = (
        pkg_id != old_id
        or _is_dev_source(source)
        or tree_has_legacy_imports(source, old_id)
    )

    if not need_rewrite:
        return source, pkg_id, None

    tmp = tempfile.TemporaryDirectory(prefix="hamod_pack_")
    work = Path(tmp.name) / pkg_id
    shutil.copytree(
        source,
        work,
        ignore=shutil.ignore_patterns(*_SKIP_DIR_NAMES, "*.pyc", "*.pyo", "*.hamod", ".git"),
    )

    rewrite_tree_in_place(work, module_id=old_id, new_id=pkg_id)

    # manifest
    mf_path = work / "manifest.yaml"
    data = yaml.safe_load(mf_path.read_text(encoding="utf-8"))
    data = _rewrite_manifest_dict(data, new_id=pkg_id, new_name=new_name, old_id=old_id)
    mf_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    # 目录名校验：work 已是 pkg_id
    return work, pkg_id, tmp


def pack_extension(
    source_dir: Path | str,
    *,
    output_dir: Path | str | None = None,
    output_path: Path | str | None = None,
    new_id: str | None = None,
    new_name: str | None = None,
) -> Path:
    """打包扩展目录为 <id>-<version>.hamod。

    new_id/new_name：改写成自包含包，便于并行安装多份（调试用）。
    从 extension_packages/<id> 或 modules/<id> 打包时会改写导入，使 extensions/ 可独立运行。
    """
    root = Path(source_dir).resolve()
    if not root.is_dir():
        raise PackError(f"不是目录: {root}")

    tmp_ctx: tempfile.TemporaryDirectory[str] | None = None
    try:
        work, pkg_id, tmp_ctx = _prepare_pack_tree(root, new_id=new_id, new_name=new_name)
        try:
            manifest = load_manifest(work)
        except ManifestError as exc:
            raise PackError(str(exc)) from exc
        if manifest.id != pkg_id:
            raise PackError(f"打包后 id 不一致: {manifest.id} vs {pkg_id}")

        if output_path is not None:
            out = Path(output_path)
        else:
            out_dir = Path(output_dir) if output_dir else root.parent
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{manifest.id}-{_safe_version_slug(manifest.version)}{PACKAGE_SUFFIX}"

        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()

        prefix = manifest.id
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(work.rglob("*")):
                if _should_skip(path, work):
                    continue
                if path.is_dir():
                    continue
                rel = path.relative_to(work).as_posix()
                zf.write(path, f"{prefix}/{rel}")
            if f"{prefix}/manifest.yaml" not in set(zf.namelist()):
                raise PackError("打包结果缺少 manifest.yaml")

        return out.resolve()
    finally:
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
