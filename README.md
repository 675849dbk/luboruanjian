# 视频连线

全屏视频播放 + 摄像头画中画，支持内置摄像头和 USB 外置摄像头。

## 功能

- 全屏播放本地视频文件（MP4、AVI、MKV、MOV、WMV、FLV、WebM、TS）
- 摄像头画中画悬浮窗（可拖动、可隐藏）
- 暂停时画面模糊效果 + 加载动画
- 授权码验证 + 磁盘序列号绑定（一机一装）
- 单实例运行保护
- QMediaPlayer 优先，OpenCV 自动回退

## 快捷键

| 按键 | 功能 |
|------|------|
| Space | 暂停 / 播放 |
| C | 切换摄像头显示 |
| Esc | 退出播放 |

## 运行

```bash
pip install -r requirements.txt
python recording_software.py
```

## 打包

```bash
pip install pyinstaller
pyinstaller 视频连线.spec
```

输出文件在 `dist/视频连线.exe`。

## 依赖

- Python 3.8+
- PyQt5 >= 5.15
- opencv-python >= 4.5
- numpy >= 1.19
