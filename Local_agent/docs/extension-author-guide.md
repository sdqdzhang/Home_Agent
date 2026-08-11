# 扩展模块编写指南

面向扩展作者：怎么写、怎么打包、怎么安装/卸载，以及必须避开的坑。

更细的字段定义见 [`extension-contract.md`](./extension-contract.md)；样板代码：`extension_packages/crawler/`。

---

## 1. 一句话理解

扩展 = **一个 `.hamod` 安装包**（zip）。

| 阶段 | 位置 | 说明 |
|------|------|------|
| 开发 | `Local_agent/extension_packages/<id>/` | 只给人改代码 / 打包用，**运行时不加载** |
| 安装后 | `Local_agent/extensions/<id>/` | 真正跑的代码；卸载会删掉 |
| 安装态 | `Local_agent/extensions/installed.json` | 记了哪些扩展已装 |

用户只需拿到一个 `.hamod`，用 CLI 或前端「扩展管理」安装即可，**不需要**再复制源码。

---

## 2. 目录与文件

### 2.1 最低结构

```text
my_ext/
  manifest.yaml      # 必填：id / 版本 / 槽位 / 依赖 / UI / settings 等
  capability.py      # 必填：TOOLS + create_service（+ 可选 invoke_tool）
  settings.defaults.yaml  # 可选：包内默认配置（开箱即用）
  service.py         # 推荐：业务 Service
  requirements.txt   # 可选：额外 pip 依赖
  router.py          # 可选：HTTP API（manifest.http.router 声明）
  main_tools.py      # 可选：主对话工具结果美化
  ...                # 其它包内模块
```

### 2.2 `manifest.yaml` 要点

```yaml
api_version: 1
id: my_ext                 # [a-z][a-z0-9_]*，与目录名一致
name: 我的扩展
version: "0.1.0"
tier: extension

entry:
  capability: capability   # → capability.py

provides_tools: true

llm_slots:                 # 会进「模型配置」页
  - key: my_ext.main       # 建议 <id>.<name>，全局唯一
    capability: chat
    label: 主模型

requires:
  python: ">=3.11"
  packages:                # 安装时 pip 进当前 Local venv
    - httpx

ui:
  label: 我的扩展
  icon: "◍"
  workspace: none          # 新扩展一律 none（见下）

ws:
  channels: auto
  on_message: handle_incoming_message

# 可选 HTTP
# http:
#   router: router:router   # 包内 router.py 里的 router 对象
```

**前端界面约定：**

- **新扩展**：`workspace: none` —— 侧栏可见，点开用通用扩展面板；**不要**往 `.hamod` 里塞 Vue。
- **crawler**：历史特例，`workspace: host`，主前端已有 `CrawlerWorkspace`，继续留用即可。

### 2.3 `capability.py` 要点

```python
from shared.extensions.contract import ExtensionManifest, ToolSpec

TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="my_ext_do_something",   # 主对话里看到的工具名
        module_id="my_ext",           # 必须等于 manifest.id
        method="do_something",        # Service 上的方法名
        description="……",
        parameters={...},             # JSON Schema
        tier="extension",             # 必须 extension
        when="何时选用",
    ),
]

def create_service(*, server_client, manifest: ExtensionManifest):
    from service import MyService
    return MyService(server_client=server_client)

# 可选：美化主对话输出
# async def invoke_tool(service, name, arguments, *, request_id="", ctx=None): ...

# 可选生命周期
# async def on_loaded(service, *, ctx): ...
# async def on_unload(service, *, ctx): ...
```

加载成功后：`TOOLS` 会合并进主对话 Function Calling；模型通过 `call(module_id, method, ...)` 调用，**不要**在 `modules/main` 里写扩展专用分支。

### 2.4 模块配置（非模型）

在 `manifest.yaml` 声明 `settings` 字段列表；包内可放 `settings.defaults.yaml` 作为开箱默认。

用户配置写入 `data/<id>/settings.json`（升级保留；卸载默认保留，勾选删 data 才清）。

**模型 / 槽位绑定仍只在「模型配置」页**；扩展管理列表的「配置」只改模块自身参数（API Key、超时等）。

支持的控件类型：`string` / `text` / `number` / `integer` / `boolean` / `secret` / `select` / `radio` / `multiselect` / `checkbox_group`。

```yaml
settings:
  - key: api_key
    type: secret
    label: API Key
    required: true
    group: 账号
  - key: engine
    type: select
    label: 引擎
    default: bing
    options: [bing, serpapi]
  - key: enabled_modes
    type: checkbox_group
    label: 模式
    default: [fast]
    options:
      - { value: fast, label: 快速 }
      - { value: deep, label: 深度 }
```

保存后可实现 `on_settings_changed(service, values)`；加载时用 `shared.extensions.settings_store.get_merged_values(id)` 读取生效值。

---

## 3. 推荐开发流程

```text
1. 在 extension_packages/<id>/ 写代码
2. pack → 得到 dist/<id>-<version>.hamod
3. install（CLI 或前端上传）
4. 重启或等 apply；看日志是否 extension loaded
5. 主对话确认工具出现；需要时再配 LLM 槽位
6. 改代码 → 升 version → 重新 pack → 再 install（同 id 覆盖升级）
7. uninstall → extensions/<id>/ 被删干净
```

### 3.1 打包

在 `Local_agent` 目录、已激活 venv：

```powershell
cd Local_agent

# 正式包
python -m shared.extensions pack extension_packages\my_ext -o dist
# → dist/my_ext-0.1.0.hamod

# 调试：同一份源码打成两个 id（可并行安装）
python -m shared.extensions pack extension_packages\my_ext -o dist --id my_ext_a --name "扩展A"
```

打包器会：

- 把开发树里的 `modules.<id>.*` / `extension_packages.<id>.*` 导入**改写成包内相对导入**；
- 规避与标准库同名的子包（例如业务包勿叫 `logging`，应使用 `crawl_logging` 这类名字）。

### 3.2 安装

```powershell
python -m shared.extensions install dist\my_ext-0.1.0.hamod
```

或前端 **扩展管理** → 上传同一个 `.hamod`（与 CLI 同一套安装器）。

安装时会：解压到 `extensions/<id>/` → `pip install` 依赖 → 写 `installed.json` → 尽量同进程 `apply_reload`（加载 Service / WS / TOOLS / LLM 槽位 / 可选 HTTP router）。

CLI 安装若提示 `restart_required`，**重启 Local Agent** 后再用。

### 3.3 卸载

```powershell
python -m shared.extensions uninstall my_ext
# 可选：--purge-data   同时删 data/<id>
# 可选：--purge-deps   尝试 pip uninstall 本扩展记录的依赖（慎用）
# 可选：--keep-code    只注销，不删 extensions/<id>/
```

| 路径 | 卸载默认行为 |
|------|----------------|
| `extensions/<id>/` | **删除** |
| `extensions/installed.json` 中条目 | **删除** |
| `data/<id>/` | 保留（除非 `--purge-data`） |
| `extension_packages/<id>/` | **不动**（开发源码） |
| pip 依赖 | **不动**（除非 `--purge-deps`） |

### 3.4 开发快捷方式（可不经 `.hamod` 文件）

```powershell
python -m shared.extensions register-bundled extension_packages/my_ext
```

等价于 pack → 解压到 `extensions/` 并写安装态；正式分发仍应发 `.hamod`。

---

## 4. 注意事项（必读）

### 4.1 导入与包结构

1. **运行时只认 `extensions/<id>/`**，不要依赖仓库里还有 `modules/<id>`。
2. 开发树可用 `from modules.xxx` / `from extension_packages.xxx`；**打包后会改成包内导入**。为清晰起见，新代码也可直接写相对风格并保证自包含。
3. **子目录不要与标准库同名**（尤其禁止包名 `logging`）。crawler 使用 `crawl_logging/`。撞名会导致 `from logging import JobLogger` 之类错误。
4. 顶层模块名尽量短、唯一；`capability` / `service` / `router` 为约定入口。

### 4.2 主对话与工具

1. `ToolSpec.module_id` 必须等于 `manifest.id`；`tier` 必须为 `extension`。
2. `method` 必须是 Service 上可调用的方法。
3. 卡片 / 进度展示写在包内 `invoke_tool`（或 `main_tools.py`），**不要**改 `modules/main/runtime.py` 塞专用逻辑。
4. 扩展未加载成功时，工具不会出现在主对话；先看 Local 日志 `extension loaded` / `failed to load`。

### 4.3 依赖与环境

1. 依赖写在 `manifest.requires.packages` 和/或 `requirements.txt`；安装进**当前正在跑 Local 的那个 Python**。
2. `post_install` 仅白名单（如 `playwright_install`），禁止任意 shell。
3. 不做多 venv / 商店 / 签名校验；本机信任上传的包。

### 4.4 前端

1. **新扩展不提供专用 Vue 页**；`workspace: none`。
2. 侧栏由 `GET /extensions` 动态列出；加载失败会显示错误状态。
3. crawler 专用页是主前端硬编码，**不在** `.hamod` 内。

### 4.5 开发模式注意

用 `uvicorn --reload` 时，安装/卸载会改 `extensions/` 下大量文件，可能触发**整进程重启**。属开发模式副作用；生产勿开 `--reload`。若安装后列表「一闪而过」，先看加载报错日志，再确认是否用了**最新打包的 `.hamod`**。

### 4.6 id 与升级

1. `id` 全局唯一，勿与 core 模块（`main` / `env` / `rag` …）冲突。
2. 同 `id` 再安装 = 覆盖升级（先换目录再 apply）。
3. 调试多实例用 `pack --id other_id`，工具名 / 槽位 key 会一并改写。

---

## 5. 验收清单

安装并重启（或 apply）后，确认：

- [ ] 日志有 `extension loaded: <id>`
- [ ] `GET /health` 或扩展列表里 `loaded: true` / `status: ready`
- [ ] 主对话能看到该扩展的工具名
- [ ] 调一次工具能走到 Service 方法
- [ ] LLM 配置页能看到 `llm_slots`（若声明了）
- [ ] `uninstall` 后 `extensions/<id>/` 不存在，主对话工具消失

---

## 6. 相关文档与命令速查

| 文档 | 内容 |
|------|------|
| 本文 | 编写 / 流程 / 注意点 |
| [`extension-contract.md`](./extension-contract.md) | 契约字段与产品边界 |
| [`extension-packaging.md`](./extension-packaging.md) | 打包命令备忘 |
| `shared/extensions/contract.py` | 类型定义 |

```powershell
python -m shared.extensions pack <源目录> -o dist [--id ...] [--name ...]
python -m shared.extensions install <文件.hamod>
python -m shared.extensions uninstall <id> [--purge-data] [--purge-deps] [--keep-code]
python -m shared.extensions list
python -m shared.extensions register-bundled <源目录>
```
