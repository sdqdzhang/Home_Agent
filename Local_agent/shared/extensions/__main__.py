"""CLI: python -m shared.extensions install foo.hamod | uninstall crawler | list"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m shared.extensions")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install", help="安装 .hamod")
    p_install.add_argument("package", type=Path)

    p_uninstall = sub.add_parser("uninstall", help="卸载扩展")
    p_uninstall.add_argument("module_id")
    p_uninstall.add_argument("--purge-data", action="store_true")
    p_uninstall.add_argument("--purge-deps", action="store_true")
    p_uninstall.add_argument("--no-purge-slots", action="store_true")

    sub.add_parser("list", help="列出已安装扩展")

    args = parser.parse_args(argv)

    # 保证 Local_agent 根在 path
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from app.config import settings
    from shared.extensions.installer import ensure_default_bundled, install_hamod, list_extensions_public, uninstall

    ensure_default_bundled(settings.base_dir)

    if args.cmd == "list":
        print(json.dumps(list_extensions_public(settings.base_dir), ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "install":

        async def _run():
            return await install_hamod(args.package, base_dir=settings.base_dir, apply=False)

        result = asyncio.run(_run())
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        print("apply=restart_required（CLI 未挂 loader host，请重启 Local Agent）")
        return 0

    if args.cmd == "uninstall":

        async def _run():
            return await uninstall(
                args.module_id,
                base_dir=settings.base_dir,
                purge_data=args.purge_data,
                purge_deps=args.purge_deps,
                purge_slots=not args.no_purge_slots,
                apply=False,
            )

        result = asyncio.run(_run())
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
