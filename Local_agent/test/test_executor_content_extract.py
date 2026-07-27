import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.executor.capabilities.files import _normalize_content_search
from modules.executor.content_extract import (
    extract_fenced_blocks,
    extract_search_query_from_text,
    pick_file_body,
    strip_fenced_blocks,
)
from modules.executor.schemas import ContentSearchAction

SAMPLE = '''请写入 workspace/123.py

```python
"""
A+B Problem
"""
def add(a, b):
    """Return the sum."""
    return a + b
```
'''


def test_extract_preserves_triple_quotes():
    blocks = extract_fenced_blocks(SAMPLE)
    assert len(blocks) == 1
    assert '"""' in blocks[0]
    assert 'A+B Problem' in blocks[0]

    instruction = strip_fenced_blocks(SAMPLE)
    assert 'def add' not in instruction
    assert '123.py' in instruction

    body, source = pick_file_body(fenced_blocks=blocks, llm_content='corrupted')
    assert source == 'fenced_block'
    assert body == blocks[0]
    assert '"""' in body


def test_normalize_content_search_fills_empty_query():
    path = r"C:\Users\qd_zh\Desktop\项目\homeagent\Local_agent\workspace\docs\module-communication.md"
    action_text = f'在{path}中查找"方式"'
    payload = _normalize_content_search(
        {"path": path, "query": "", "context_lines": 5},
        action_text=action_text,
    )
    action = ContentSearchAction.model_validate(payload)
    assert action.query == "方式"


def test_extract_search_query_from_text():
    path = r"C:\Users\qd_zh\Desktop\项目\homeagent\Local_agent\workspace\docs\module-communication.md"
    assert extract_search_query_from_text(f'在{path}中查找"方式"') == "方式"
    assert extract_search_query_from_text(f"在 {path} 中查找「方式」") == "方式"
    assert extract_search_query_from_text("在 readme.md 里搜索 JWT_SECRET") == "JWT_SECRET"
    assert extract_search_query_from_text("查找方式") == "方式"


if __name__ == '__main__':
    test_extract_preserves_triple_quotes()
    test_normalize_content_search_fills_empty_query()
    test_extract_search_query_from_text()
    print('ok')
