import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.executor.content_extract import extract_fenced_blocks, pick_file_body, strip_fenced_blocks

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


if __name__ == '__main__':
    test_extract_preserves_triple_quotes()
    print('ok')
