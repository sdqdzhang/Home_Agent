"""CLI: python -m shared.extensions pack|install|uninstall|list"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shared.extensions")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pack = sub.add_parser("pack", help="把扩展目录打成 .hamod")
    p_pack.add_argument("source", type=Path, help="含 manifest.yaml 的扩展目录")
    p_pack.add_argument("-o", "--output-dir", type=Path, default=None, help="输出目录（默认源目录的父目录）")
    p_pack.add_argument("--out", type=Path, default=None, help="指定完整输出路径（含文件名）")
    p_pack.add_argument("--id", dest="new_id", default=None, help="改写扩展 id（自包含，可并行装多份）")
    p_pack.add_argument("--name", dest="new_name", default=None, help="改写显示名")

    p_install = sub.add_parser("install", help="安装 .hamod")
    p_install.add_argument("package", type=Path)

    p_uninstall = sub.add_parser("uninstall", help="卸载扩展（默认删除代码目录）")
    p_uninstall.add_argument("module_id")
    p_uninstall.add_argument("--purge-data", action="store_true", help="同时删除 data/<id>")
    p_uninstall.add_argument("--purge-deps", action="store_true", help="尝试 pip uninstall 记录的依赖")
    p_uninstall.add_argument("--keep-code", action="store_true", help="保留代码目录（仅注销）")
    p_uninstall.add_argument("--no-purge-slots", action="store_true")

    p_reg = sub.add_parser("register-bundled", help="把仓库扩展物化到 extensions/（可干净卸载）")
    p_reg.add_argument("path", type=Path, help="如 extension_packages/crawler")
    p_reg.add_argument("--id", dest="new_id", default=None, help="可选改写 id")
    p_reg.add_argument("--name", dest="new_name", default=None, help="可选改写显示名")

    sub.add_parser("list", help="列出已安装扩展")

    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from app.config import settings
    from shared.extensions.installer import (
        ensure_default_bundled,
        install_hamod,
        list_extensions_public,
        uninstall,
    )
    from shared.extensions.pack import PackError, pack_extension

    if args.cmd == "pack":
        try:
            out = pack_extension(
                args.source,
                output_dir=args.output_dir,
                output_path=args.out,
                new_id=args.new_id,
                new_name=args.new_name,
            )
        except PackError as exc:
            print(f"pack failed: {exc}", file=sys.stderr)
            return 1
        print(str(out))
        return 0

    ensure_default_bundled(settings.base_dir)

    if args.cmd == "list":
        payload = json.dumps(list_extensions_public(settings.base_dir), ensure_ascii=False, indent=2)
        sys.stdout.buffer.write((payload + "\n").encode("utf-8", errors="replace"))
        return 0

    if args.cmd == "install":

        async def _run_install():
            return await install_hamod(args.package, base_dir=settings.base_dir, apply=False)

        result = asyncio.run(_run_install())
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        print("apply=restart_required（CLI 未挂 loader host，请重启 Local Agent）")
        return 0

    if args.cmd == "uninstall":

        async def _run_uninstall():
            return await uninstall(
                args.module_id,
                base_dir=settings.base_dir,
                purge_data=args.purge_data,
                purge_deps=args.purge_deps,
                purge_slots=not args.no_purge_slots,
                purge_code=not args.keep_code,
                apply=False,
            )

        result = asyncio.run(_run_uninstall())
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "register-bundled":
        root = args.path
        if not root.is_absolute():
            root = (settings.base_dir / root).resolve()
        from shared.extensions.installer import InstallError, materialize_from_source

        try:
            mid = materialize_from_source(
                root,
                settings.base_dir,
                new_id=args.new_id,
                new_name=args.new_name,
            )
        except (InstallError, Exception) as exc:
            print(f"register-bundled failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps({"id": mid, "path": f"extensions/{mid}"}, ensure_ascii=False))
        print("已写入 extensions/ 与 installed.json；请重启 Local Agent")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
