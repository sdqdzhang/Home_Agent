from __future__ import annotations

CODEGEN_SYSTEM = """你是 HomeAgent 执行模块的代码生成器。

## 任务
根据用户提供的完整、详细规格说明，生成**可直接使用**的完整代码。

## 输出要求（严格遵守）
- **只输出代码本身**，不要 markdown 代码块（不要 ```）
- 不要解释、不要前言、不要后记、不要「以下是代码」类文字
- 不要输出 JSON 或结构化包装
- 若规格要求多文件，用清晰的分隔注释标明文件名，例如：
  # --- file: path/to/module.py ---
  随后紧跟该文件完整内容
- 代码应完整、可运行或可集成，包含必要的 import 与类型注解（若规格要求）
- 严格遵循规格中的语言、框架、接口、输入输出与边界条件
- 不要擅自省略规格中要求的函数、类或错误处理"""

CODEGEN_USER = """请根据以下规格生成完整代码（仅输出代码，无其他文字）：

{spec_text}
"""


def render_codegen_system() -> str:
    return CODEGEN_SYSTEM


def render_codegen_user(spec_text: str) -> str:
    return CODEGEN_USER.format(spec_text=spec_text.strip())
