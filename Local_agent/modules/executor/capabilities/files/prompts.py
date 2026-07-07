from __future__ import annotations

from modules.executor.environment import get_exec_environment

_ENV_RULES = """- 相对路径相对于默认工作目录
- 用户说「当前目录」「这里」「本目录」均指默认工作目录；生成 path 时优先写绝对路径
- 路径可使用正斜杠或 Windows 反斜杠"""


def _env_block() -> str:
    env = get_exec_environment()
    return f"""【执行环境】
OS: {env.os_name}
Shell: {env.shell_label}
工作目录: {env.default_cwd}

{_ENV_RULES}

{env.path_rules()}"""


def _json_rules(action_desc: str) -> str:
    return f"""## 输出格式（严格遵守）
- **只输出 JSON**，不要 markdown 代码块，不要解释文字
- 若无法唯一执行，输出 {{"ok": false, "reason": "具体原因（中文）"}}
- 若可执行，输出 {action_desc}"""


def read_file_system() -> str:
    return f"""你是 HomeAgent 执行模块的「读取文件」解析器。
把明确动作转为 JSON：{{"ok": true, "type": "file.read", "path": "...", "encoding": "utf-8"}}

{_json_rules('{"ok": true, "type": "file.read", "path": "绝对或相对路径", "encoding": "utf-8"}')}"""


def read_file_user(action_text: str, **_kwargs) -> str:
    return f"{_env_block()}\n\n读取文件：\n{action_text.strip()}"


def write_file_system() -> str:
    return f"""你是 HomeAgent 执行模块的「写入文件」解析器。
把明确动作转为 JSON：{{"ok": true, "type": "file.write", "path": "...", "encoding": "utf-8"}}

- 你只解析 path（及 encoding）；正文由系统从侧栏/附件/代码块注入，**禁止输出 content**
- 新建空文件：用户明确要空文件且无附带正文时，只输出 path

{_json_rules('{"ok": true, "type": "file.write", "path": "...", "encoding": "utf-8"}')}"""


def write_file_user(action_text: str, *, has_attached_body: bool = False, **_kwargs) -> str:
    body = f"{_env_block()}\n\n写入文件：\n{action_text.strip()}"
    if has_attached_body:
        body += (
            "\n\n（说明：用户已通过侧栏/附件或 ``` 代码块提供正文。"
            "你只解析 path 与 encoding，**禁止**在 JSON 中出现 content。）"
        )
    return body


def delete_file_system() -> str:
    return f"""你是 HomeAgent 执行模块的「删除文件」解析器。
把明确动作转为 JSON：{{"ok": true, "type": "file.delete", "path": "..."}}

- 仅删除单个文件，不删除目录

{_json_rules('{"ok": true, "type": "file.delete", "path": "绝对或相对路径"}')}"""


def delete_file_user(action_text: str, **_kwargs) -> str:
    return f"{_env_block()}\n\n删除文件：\n{action_text.strip()}"


def browse_dir_system() -> str:
    return f"""你是 HomeAgent 执行模块的「浏览目录」解析器。
把明确动作转为 JSON：{{"ok": true, "type": "dir.browse", "path": null, "max_depth": 4}}

- path 省略或 null 表示默认工作目录
- max_depth 默认 4，范围 1-12

{_json_rules('{"ok": true, "type": "dir.browse", "path": "目录或null", "max_depth": 4}')}"""


def browse_dir_user(action_text: str, **_kwargs) -> str:
    return f"{_env_block()}\n\n浏览目录：\n{action_text.strip()}"


def search_file_system() -> str:
    return f"""你是 HomeAgent 执行模块的「搜索文件」解析器。
把明确动作转为 JSON：{{"ok": true, "type": "file.search", "pattern": "...", "root": null}}

- 从 root 目录**递归**搜索文件名匹配 pattern 的文件
- root 省略或 null 表示默认工作目录
- pattern 可为精确文件名（如 docker-compose.yml）或通配符（如 *.py）

{_json_rules('{"ok": true, "type": "file.search", "pattern": "文件名或通配符", "root": "目录或null"}')}"""


def search_file_user(action_text: str, **_kwargs) -> str:
    return f"{_env_block()}\n\n搜索文件：\n{action_text.strip()}"


def search_content_system() -> str:
    return f"""你是 HomeAgent 执行模块的「搜索内容」解析器。
把明确动作转为 JSON：{{"ok": true, "type": "content.search", "path": "...", "query": "...", "context_lines": 5}}

- **必须**指定要搜索的单个文件 path
- **必须**填写 query（要查找的文本）；引号/书名号内的词、或「查找/搜索」后的词都要写入 query，**禁止留空**
- context_lines 默认 5（命中行上下各 5 行上下文）

示例：
- 用户：在 D:\\\\docs\\\\a.md 中查找「方式」
  → {{"ok": true, "type": "content.search", "path": "D:\\\\docs\\\\a.md", "query": "方式", "context_lines": 5}}
- 用户：在 module-communication.md 里搜索 "JWT_SECRET"
  → {{"ok": true, "type": "content.search", "path": "module-communication.md", "query": "JWT_SECRET", "context_lines": 5}}

{_json_rules('{"ok": true, "type": "content.search", "path": "文件路径", "query": "搜索文本", "context_lines": 5}')}"""


def search_content_user(action_text: str, **_kwargs) -> str:
    return f"{_env_block()}\n\n在文件中搜索内容：\n{action_text.strip()}"
