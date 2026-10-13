# live2d_test

独立沙盒：试验 **无边框透明桌宠** 和 **dsh-pet 神神 WebM**（置顶、拖拽、戳一戳、闲置动画链、边缘探头、Mind → 动作）。

- **不依赖、不修改**仓库其余代码，用完可整夹删除
- 不挂进 `联调启动.bat`，也不连 Local Agent / Server Center
- Mind 状态在实验室窗口里手调；映射在 `mapper.py`，动作挑选在 `director.py`

## 启动

需要：Windows、Python 3.10+。旁边要有 `dsh-pet-indesktop-main`（或已经拷过素材）。首次启动会安装 **PySide6** 和 **imageio-ffmpeg**。

```bat
cd live2d_test
start.bat
```

会打开：

| 窗口 | 作用 |
|------|------|
| **lab** | 普通窗口：动作列表、Mind、唤出桌宠 |
| **pet** | 无边框透明小人，不进任务栏；右键可复位 |

角色外是桌面，不是深色方框。透明像素鼠标会穿透。若要深色底：`.venv\Scripts\python.exe app.py --opaque`。

素材在 `overlay/models/shenshen/`，被 gitignore。缺文件时运行 `python fetch_shenshen.py`。

只要页面、不要桌宠：

```bat
.venv\Scripts\python.exe app.py --browser
```

单测：

```bat
.venv\Scripts\python.exe -m unittest discover -s . -p "test_*.py"
```

## 从 dsh-pet 学到的行为

1. **动画链**（待命）：播完一条后 30% 待机、10% 转向、40% 随机动作、20% 走路。走路条前 2 秒/后 2 秒原地，中间平移窗口。
2. **点击**：立刻打断当前条，从 `click/` 随机一条。
3. **拖拽**：切到悬空反馈；松手后若贴着左右屏进入 **边缘探头**（±42°，露出约一半，点击拉直约 5 秒）。
4. **忙碌联动**：实验室切「执行中」→ `写代码` / `吃Token` 交替。
5. **点击不抢焦点**：`WS_EX_NOACTIVATE`。
6. **透明 WebM**：ffmpeg 解成 RGBA 再画到 Qt 窗口（和 dsh-pet 同一路线），不用 WebView2。

非官方同人形象，与 DeepSeek 官方无隶属关系。仅本机沙盒学习用，不要随 HomeAgent 再分发。

## 文件

```text
live2d_test/
  catalog.py         扫描 videos/ 子目录，掷骰动画链
  mapper.py          MindState → PresentationIntent
  director.py        Intent → 具体 WebM 名
  player.py          队列 / 打断 / 拖拽
  windowing.py       Win32 探头、NOACTIVATE、穿透
  webm_player.py     imageio-ffmpeg → RGBA 帧
  pet_window.py      Qt 透明桌宠
  lab_window.py      Qt 实验室
  app.py             HTTP + Qt 事件循环
  fetch_shenshen.py  复制神神 WebM
  overlay/           --browser 用的页面
```
