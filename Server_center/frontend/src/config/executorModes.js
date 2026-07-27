/** 执行模块子能力（与 Local_agent ExecuteRequest.mode 对齐） */

/** @typedef {'command'|'read_file'|'write_file'|'delete_file'|'browse_dir'|'search_file'|'search_content'} ExecutorModeId */

/** @typedef {{ id: ExecutorModeId, label: string, hint: string }} ExecutorModeDef */

/** 发送时不传 mode = 自动路由 */
export const EXECUTOR_MODE_AUTO = 'auto'

/** @type {ExecutorModeDef[]} */
export const EXECUTOR_MODES = [
  {
    id: 'command',
    label: '命令执行',
    hint: '单一 shell 命令',
  },
  {
    id: 'read_file',
    label: '读取文件',
    hint: '读取指定文件内容',
  },
  {
    id: 'write_file',
    label: '写入文件',
    hint: '创建或覆盖写入文件',
  },
  {
    id: 'delete_file',
    label: '删除文件',
    hint: '删除单个文件（需安检）',
  },
  {
    id: 'browse_dir',
    label: '浏览目录',
    hint: '目录树结构',
  },
  {
    id: 'search_file',
    label: '搜索文件',
    hint: '按文件名搜索',
  },
  {
    id: 'search_content',
    label: '搜索内容',
    hint: '文件内文本搜索',
  },
]

/** @param {string} id */
export function findExecutorMode(id) {
  return EXECUTOR_MODES.find((m) => m.id === id) || null
}

/** @param {string | null | undefined} id */
export function executorModeLabel(id) {
  if (!id || id === EXECUTOR_MODE_AUTO) return '自动路由'
  return findExecutorMode(id)?.label || id
}
