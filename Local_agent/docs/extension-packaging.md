# 扩展打包指南

> **推荐先读：** [`extension-author-guide.md`](./extension-author-guide.md)（编写注意、流程、验收清单）。  
> 本文保留命令备忘；字段权威定义见 [`extension-contract.md`](./extension-contract.md)。

把任意符合契约的扩展目录打成 **一个 `.hamod` 文件**，再用 CLI / 前端 / HTTP 安装。
安装永远落在 `extensions/<id>/`；卸载会**删除该目录代码**（清干净，可再装升级版）。
`modules/` 只作 core；扩展开发源码放 `extension_packages/<id>/`（仅打包用，运行时不会加载）。

## 目录最低要求

```
my_ext/
  manifest.yaml      # 必填
  capability.py      # 必填（create_service + TOOLS + 可选 invoke_tool）
  main_tools.py      # 可选：主对话美化输出（invoke_tool 调用）
  requirements.txt   # 可选
  service.py / ...
```

主对话里要展示的任务卡片 / 进度，应写在包内 `invoke_tool`（见 crawler 的 `main_tools.py`），不要写死在 `main/runtime.py`。
前端专用页（`workspace: host`）仅 crawler 等历史特例；**新扩展用 `workspace: none`**，通用面板即可。

## 命令行打包

```powershell
cd Local_agent

# 从开发树打包（会改写 modules.crawler / extension_packages 导入为自包含）
python -m shared.extensions pack extension_packages\crawler -o dist

# 调试：同时装两份不同名爬取模块
python -m shared.extensions pack extension_packages\crawler -o dist --id crawler_a --name "爬取A"
python -m shared.extensions pack extension_packages\crawler -o dist --id crawler_b --name "爬取B"
# → dist/crawler_a-0.1.0.hamod  /  dist/crawler_b-0.1.0.hamod
# 工具名会变成 crawler_a_fetch / crawler_b_fetch，槽位 crawler_a.pipeline 等
```

## 安装 / 升级 / 卸载

```powershell
python -m shared.extensions install dist\crawler_a-0.1.0.hamod
python -m shared.extensions install dist\crawler_a-0.2.0.hamod   # 同 id 覆盖升级
python -m shared.extensions uninstall crawler_a                  # 删除 extensions/crawler_a
```

或前端「扩展管理」上传 / 卸载（同一套安装器）。

物化开发树（等价 pack+install 到 extensions，不经 hamod 文件）：

```powershell
python -m shared.extensions register-bundled extension_packages/crawler
python -m shared.extensions register-bundled extension_packages/crawler --id crawler_dev --name "爬取调试"
```

## WinError 32

上传安装时临时 `.hamod` 曾因未关闭文件句柄导致删除失败；已修复。若仍偶发，重试安装即可。
