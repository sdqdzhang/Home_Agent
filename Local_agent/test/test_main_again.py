"""[again] 标记解析测试。"""

from modules.main.model.assistant import has_again_marker, strip_again_marker


def test_has_again_standalone_line():
    assert has_again_marker("先说明一下\n[again]")
    assert has_again_marker("[again]")
    assert has_again_marker("  [again]  \n")
    assert has_again_marker("说明\n［again］")
    assert has_again_marker("说明\n【again】")
    assert has_again_marker("说明\n`[again]`")
    assert has_again_marker("说明\n**[again]**")
    assert not has_again_marker("请写 [again] 在句中")
    assert not has_again_marker("again")
    assert not has_again_marker("")


def test_strip_again_marker():
    assert strip_again_marker("完成了一步\n[again]") == "完成了一步"
    assert strip_again_marker("[again]") == ""
    assert strip_again_marker("你好\n\n[again]\n\n") == "你好"
    assert strip_again_marker("完成\n【again】") == "完成"
    assert strip_again_marker("请写 [again] 在句中") == "请写 [again] 在句中"
