# 本沙盒要的角色素材

只认 **dsh-pet 神神** 这一套：透明 VP9 WebM，不是 Live2D Cubism。

```text
overlay/models/shenshen/videos/
  idle/     待机
  turn/     转向（东张西望）
  move/     走路（会平移窗口；文件名带「原地」的不算位移）
  click/    点击回应
  drag/     拖拽悬空
  random/   随机动作池（闲置 40%）
  events/   余额等，并入动作池
```

`python fetch_shenshen.py` 从旁边的 `dsh-pet-indesktop-main/assets/characters/shenshen/videos` 复制。启动时若沙盒里没有，也会自动拷。

入口不需要 `pet.json`。播放器按文件夹分类，Mind 映射在 `director.py`：

| Intent | 素材 |
|---|---|
| idle | 动画链 30/10/40/20 |
| work / executing | 写代码 ↔ 吃Token，每 3 次轻快记录 |
| think | 深度思考碎碎念 |
| wrap | 工作状态-清点归档 |
| talking | 哼歌 / 礼仪 |
| alert | 垂头叹气等 |
| gaze=aside | 东张西望 |
| poke | click/ 随机 |
| flinch | 被吓一跳 |
| nod | 工作状态-雀跃庆祝 |

画布 640×360，脚底 y=330，默认缩放 0.72（与 dsh-pet 一致）。

来源：[MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop) / [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)。非官方同人，仅本机沙盒用，不要随 HomeAgent 再分发。
