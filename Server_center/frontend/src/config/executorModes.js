/** 执行模块子能力（与 Local_agent ExecuteRequest.mode 对齐） */

/** @typedef {'command'|'read_file'|'write_file'|'delete_file'|'browse_dir'|'search_file'|'search_content'|'codegen'} ExecutorModeId */

/** @typedef {{ id: ExecutorModeId, label: string, hint: string, emptyHint: string, sidebar?: boolean }} ExecutorModeDef */

/** @type {ExecutorModeDef[]} */
export const EXECUTOR_MODES = [
  {
    id: 'command',
    label: '命令执行',
    hint: '用自然语言描述单一 shell 命令（不含读/写/删文件，那些请用专用 Tab）',
    emptyHint: '例如「列出当前目录下的 .py 文件」或「运行 python -m pytest」',
  },
  {
    id: 'read_file',
    label: '读取文件',
    hint: '读取指定文件内容，结果在回复中返回',
    emptyHint: '例如「读取 README.md」或「读取 config.py」',
  },
  {
    id: 'write_file',
    label: '写入文件',
    hint: '将内容写入文件（不存在则新建）；可在侧栏附上正文',
    emptyHint: '例如「将侧栏内容写入 workspace/app.py」',
    sidebar: true,
  },
  {
    id: 'delete_file',
    label: '删除文件',
    hint: '删除单个文件（黑命令，需安全审批）',
    emptyHint: '例如「删除 tmp/old.log」',
  },
  {
    id: 'browse_dir',
    label: '浏览目录',
    hint: '以 tree 风格展示目录结构',
    emptyHint: '例如「浏览整个项目结构」或「查看 src 目录」',
  },
  {
    id: 'search_file',
    label: '搜索文件',
    hint: '从指定目录递归按文件名搜索',
    emptyHint: '例如「在项目中查找 docker-compose.yml」',
  },
  {
    id: 'search_content',
    label: '搜索内容',
    hint: '在指定文件中搜索文本，返回行号及上下 5 行上下文',
    emptyHint: '例如「在 .env 中查找 JWT_SECRET 在哪里定义」',
  },
  {
    id: 'codegen',
    label: '代码生成',
    hint: '输入完整规格说明，返回纯代码（不经安检）',
    emptyHint: '例如「用 Python 实现 parse_csv(path: str) -> list[dict]，要求…」',
  },
]

/** @param {ExecutorModeId} id */
export function findExecutorMode(id) {
  return EXECUTOR_MODES.find((m) => m.id === id) || EXECUTOR_MODES[0]
}
