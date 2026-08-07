# 扩展模块契约（v1）

> 状态：**契约已定；installer / loader / HTTP / CLI 已落地（crawler 为内置样板）**。  
> 第一迁移样板：`modules/crawler`（`manifest.yaml` + `capability.py`，经 `installed.json` 启用）。  
> 类型镜像：`shared/extensions/contract.py`。

---

## 0. 产品要求对照（是否做到）

| # | 要求 | 契约结论 | 说明 |
|---|------|----------|------|
| 1 | 一键安装 / 卸载（含虚拟环境依赖） | **做到（收窄后）** | 一次 API/CLI 完成：解压 + 当前解释器 `pip install` + 写安装态 + 注册槽位 + **自动 apply（优先同进程 reload）**。只装进**正在跑 Local Agent 的那个 venv/解释器**，不做多环境管理。卸载默认**不**自动 `pip uninstall`（防误伤共享依赖）；可选 `--purge-deps`。 |
| 2 | 安装后前端可见；主对话可知可调 | **做到** | 目录以 Local 安装态为准；侧栏动态渲染；`TOOLS` 合并进主对话 FC。无专用 Workspace 时用通用扩展面板。 |
| 3 | 安装后留下 LLM 槽位，配置里可改 | **做到** | `llm_slots` **v1 必做**动态注册；LLM 配置页读「静态 core 槽 ∪ 已启用扩展槽」；卸载默认移除槽位定义，绑定记录可保留或随 `--purge-slots` 清掉。 |
| 4 | 前端上传安装 = 后端脚本安装 | **做到** | **同一** `install_hamod()`；CLI 与 `POST …/extensions/install` 都调它。前端只负责把 `.hamod` 传到 Local（可经 Server 反代）。 |

### 明确做不到 / 已改掉的原表述

| 原契约或隐含期望 | 修订 |
|------------------|------|
| 「热更新不做、重启即可」 | 改成：**一键须自动 apply**；优先扩展子集 reload；仅当 apply 判定需要时才 `restart_required`（如原生库 pip 变更）。 |
| 「前端列表实现可后置」 | 改成：**v1 必做**，否则不算安装完成。 |
| 「llm_slots 动态化可第二期 / v1 仍静态」 | 改成：**v1 必做**动态槽；静态 `slots.py` 里的扩展槽逐步迁出。 |
| 「缺 packages → unavailable、不负责安装」 | 改成：安装流程**必须**对 `requires.packages` / 包内 `requirements.txt` 执行 pip；失败则安装失败（可回滚目录）。 |
| 扩展自带 Vue 打进包并热注入 | **仍不做**（`workspace: bundle` 预留）。无 `host` 组件 → 通用面板。 |
| 任意 post-install shell / 装到任意 venv | **不做**。仅当前 `sys.executable`；`post_install` 仅白名单。 |
| 远程商店 / 签名强校验 | **不做**（本机信任上传）。 |

---

## 1. 目标与边界

**目标：** 扩展可一键安装/卸载；依赖进当前 venv；侧栏可见；主对话可调；LLM 槽可配。

**core vs extension：**

| | core | extension |
|--|------|-------------|
| 位置 | `modules/` | `extensions/<id>/` |
| 启动 | `app/main.py` 固定 | loader 按已安装且启用加载 |
| 卸载 | 不可 | 可 |

---

## 2. 包布局

```
<package-root>/                 # 安装后 = extensions/<id>/
  manifest.yaml                 # 必填
  capability.py                 # 必填
  requirements.txt              # 可选；与 manifest.requires.packages 合并去重后 pip
  service.py / ...
```

**打包：** `<id>-<version>.hamod` = zip（根含 `manifest.yaml`，或唯一顶层目录名 = `id`）。

| 路径 | 用途 |
|------|------|
| `Local_agent/extensions/<id>/` | 代码 |
| `Local_agent/extensions/installed.json` | 安装态 |
| 模块自有 data 目录 | 运行时数据；卸载默认保留 |

---

## 3. `manifest.yaml`

```yaml
api_version: 1

id: crawler                      # [a-z][a-z0-9_]*；= 目录名 = module_id
name: 网页爬取模块
aliases: [crawler, 网页爬取模块]
version: "0.1.0"
description: 网页抓取与过滤
tier: extension                  # v1 仅 extension

entry:
  capability: capability

provides:
  methods: [submit_crawl, submit_crawl_batch]

provides_tools: true

# v1 必做：安装/启用时注册进 LLM registry，配置页可绑定 endpoint
llm_slots:
  - key: crawler.pipeline        # 建议 <id>.<name>；全局唯一
    capability: chat             # 仅 chat | embed（与现 SlotDefinition 一致）
    label: 爬取管道
    description: 爬取判断、调参、过滤器择优等

  - key: crawler.chat
    capability: chat
    label: 爬取对话
    description: 爬虫模块用户对话

requires:
  local_agent: ">=0.1.0"
  python: ">=3.11"
  packages:                      # PEP 508；安装时 pip 进当前解释器
    - httpx
    - beautifulsoup4
  modules: []

# 可选；仅白名单，见 §5.3
post_install: []
# 例: [{ "action": "playwright_install", "browsers": ["chromium"] }]

permissions:
  - network
  - fs_data

ui:
  label: 网页爬取
  icon: "◍"
  default_msg_types: [execution_log]
  workspace: host                # host | none | bundle(预留)
  # host：主前端已有专用页（如 CrawlerWorkspace）
  # none：侧栏仍显示，点开为通用扩展面板

http:
  router: router:router

ws:
  channels: auto
  on_message: handle_incoming_message
  on_connect: catch_up_pending_crawls

default_msg_type: execution_log
```

### 校验

1. `api_version == 1`；`tier == extension`；`id` 合法且 = 目录名；不与 core id 冲突  
2. `capability.py` 可导入且有 `create_service`  
3. `provides_tools` 时校验 `TOOLS`（`module_id`/`tier`）  
4. 未知 `permissions` / 未知 `post_install.action` → **安装失败**  
5. `llm_slots[].key` 全局唯一（不与已加载 core/其它扩展冲突）  
6. pip 失败 → 安装失败并回滚本次解压目录  

---

## 4. `capability.py`

```python
TOOLS: list[ToolSpec] = [...]

def create_service(*, server_client, manifest: ExtensionManifest) -> Any: ...

async def on_loaded(service, *, ctx) -> None: ...   # 可选
async def on_unload(service, *, ctx) -> None: ...   # 可选
```

**FC（禁止扩展专用分支）：**

```text
ToolSpec → await call(module_id, method, **kwargs)
```

未加载的 `module_id` 从工具表剔除。

---

## 5. 安装 / 卸载（一键语义）

### 5.1 唯一实现入口

```text
shared.extensions.installer.install_hamod(path | bytes, ...) -> InstallResult
shared.extensions.installer.uninstall(id, *, purge_data=False, purge_deps=False, purge_slots=False) -> UninstallResult
shared.extensions.loader.apply() -> ApplyResult   # reload 或标 restart_required
```

| 入口 | 行为 |
|------|------|
| CLI | `python -m shared.extensions install foo.hamod` / `uninstall crawler` |
| Local HTTP | `POST /extensions/install`（multipart `.hamod`）、`DELETE /extensions/{id}`、`GET /extensions` |
| 前端 | 上传文件 → **同一** Local install 接口（经 Server 反代或直连 Local）；**禁止**在 Server 上再实现第二套解压逻辑 |

`InstallResult.apply`：`reloaded` | `restart_required`（前端提示并可选调重启接口）。

### 5.2 安装步骤（原子性尽力而为）

1. 校验 zip / manifest  
2. 解压到临时目录 → 校验通过后换入 `extensions/<id>/`（覆盖同 id 视为升级）  
3. 合并 `requires.packages` + 包内 `requirements.txt`，执行：  
   `sys.executable -m pip install -r …`（当前 Local 进程解释器 = 当前 venv）  
4. 执行白名单 `post_install`  
5. 写 `installed.json`（`enabled: true`, `status: ready`）  
6. **注册 `llm_slots` 到槽位注册表**（配置 UI 立即能看见；绑定可稍后）  
7. `apply()`：加载 Service、挂 bus/WS/router、合并 TOOLS；失败则 `status: error` 并返回原因  

### 5.3 `post_install` 白名单（v1）

| action | 含义 |
|--------|------|
| `playwright_install` | `playwright install <browsers…>`（用当前解释器） |

其它 action → 安装失败。禁止任意 shell。

### 5.4 卸载步骤

1. `on_unload`（若已加载）→ 从 bus/工具表卸下  
2. 从槽位注册表移除该扩展声明的 slots（绑定：默认保留孤儿绑定；`purge_slots` 则删）  
3. 删 `extensions/<id>/`；更新 `installed.json`  
4. `purge_data`：删模块 data  
5. `purge_deps`：按安装时记录的 **本扩展专有** pip 规格尝试 uninstall（无记录则跳过并警告）  
6. `apply()` 或 `restart_required`

### 5.5 依赖策略（venv）

- **只**使用 `sys.executable`；文档与 API 均不提供 target-venv 参数。  
- 安装成功后把实际 pip 规格写入 `installed.json` 的 `pip_specs`（供可选 purge）。  
- 共享库（如 `httpx`）卸载默认保留。  

---

## 6. 前端与主对话

### 6.1 模块列表

- `GET /extensions`（Local）返回已安装清单（含 `ui.*`、`status`、`tools` 摘要、`llm_slots`）。  
- Server `GET /api/v1/modules`（或专用 extensions 聚合）**合并** core 静态目录 + Local 上报的扩展；前端侧栏**禁止**再写死 crawler 为不可隐藏项。  
- `status != ready`：侧栏可见但标记不可用；主对话不暴露其工具。  

### 6.2 Workspace

| `ui.workspace` | 行为 |
|----------------|------|
| `host` | 主前端已有专用页则用专用页（crawler → `CrawlerWorkspace`） |
| `none` | 通用扩展面板（描述、状态、槽位入口、工具名列表、execution_log） |
| `bundle` | v1 不实现；当作 `none` |

### 6.3 主对话

- 启动/apply 后合并各扩展 `TOOLS`。  
- 模型只看到 `status==ready` 且 Service 已注册的扩展工具。  

---

## 7. LLM 槽位（v1 必做）

1. 槽位定义来源 = `shared/llm/slots.py`（core）∪ 已启用扩展的 `manifest.llm_slots`。  
2. `is_valid_slot` / 配置 UI / seed 绑定必须走**合并后**注册表。  
3. 安装或启用 → 注册定义；禁用/卸载 → 撤定义（绑定策略见 §5.4）。  
4. 扩展槽 `module` 字段 = manifest `id`。  
5. 配置中修改绑定：与现网 LLM 配置相同 API，无需为扩展另开通道。  

---

## 8. `installed.json`

```json
{
  "api_version": 1,
  "extensions": {
    "crawler": {
      "version": "0.1.0",
      "enabled": true,
      "installed_at": "2026-08-07T00:00:00+08:00",
      "path": "extensions/crawler",
      "status": "ready",
      "error": "",
      "pip_specs": ["httpx", "beautifulsoup4"]
    }
  }
}
```

---

## 9. 宿主启动顺序

1. 启动 core  
2. 读 `installed.json`，对 enabled 扩展：校验 → load → bus/WS/router → 合并 TOOLS → 合并 llm_slots  
3. 暴露 `/extensions*` 与健康检查中的扩展摘要  

---

## 10. crawler 映射

| 现有 | 契约 |
|------|------|
| `MODULE_*` | `manifest.yaml` |
| crawler `ToolSpec` | `capability.TOOLS` |
| `main.py` / `local_bus` 手写 | loader |
| `runtime` 内 crawler 分支 | 删除 → 通用 `call` |
| `slots.py` 中 crawler 槽 | 安装后由 manifest 注册（迁移期可双写，最终删静态） |
| 前端写死 agents | 动态目录；`workspace: host` 保留专用页 |

---

## 11. 验收（实现完成后）

1. CLI 与前端上传安装同一扩展，结果一致（目录、pip、槽位、工具）。  
2. 安装后侧栏出现；主对话能调其工具；LLM 配置出现其槽位并可改绑定。  
3. 卸载后侧栏消失、工具不可用、槽位定义移除（除非未 purge 的孤儿绑定策略符合文档）。  
4. 依赖装进当前 venv（`pip show` 可见）；`purge_deps` 行为符合 §5.5。  
5. core 不受影响。  
6. 无 host Workspace 的扩展仍能出现在侧栏（通用面板）。
