# -*- coding: utf-8 -*-
"""
视频连线
"""

import sys
import os
import platform
import contextlib
import hashlib
import ctypes
import tempfile

os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = ''
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'

import cv2
import numpy as np
import PyQt5
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QFrame,
    QSizePolicy, QMessageBox, QStackedWidget, QGraphicsBlurEffect,
    QDialog, QLineEdit,
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QUrl
from PyQt5.QtGui import QImage, QPixmap, QFont, QPainter, QColor, QBrush
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

IS_WINDOWS = platform.system() == 'Windows'
CAMERA_BACKEND = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY

OVERLAY_SIZES = {
    '小 (240x180)':   (240, 180),
    '中 (320x240)':   (320, 240),
    '大 (480x360)':   (480, 360),
    '超大 (640x480)': (640, 480),
}
DEFAULT_OVERLAY_SIZE = '中 (320x240)'


# ==================== 授权 & 单实例 ====================
AUTH_CODE = '15679792589'
LICENSE_DIR = os.path.join(os.environ.get('APPDATA', tempfile.gettempdir()), 'VideoConnect')
LICENSE_FILE = os.path.join(LICENSE_DIR, '.license')
MUTEX_NAME = 'Global\\VideoConnectApp_SingleInstance'


def check_single_instance():
    """Windows 命名互斥体：确保同一时间只有一个实例运行"""
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return False
    return True


def clear_license():
    """清除授权文件"""
    try:
        if os.path.exists(LICENSE_FILE):
            os.remove(LICENSE_FILE)
    except Exception:
        pass


def get_machine_id():
    """
    生成机器指纹：仅绑定磁盘序列号。
    原理：通过 wmic 读取系统盘物理序列号做 SHA256，
    只要不更换硬盘，重装系统后指纹不变。
    """
    try:
        import subprocess
        out = subprocess.check_output(
            'wmic diskdrive get serialnumber', shell=True,
            stderr=subprocess.DEVNULL
        ).decode('utf-8', errors='ignore')
        for line in out.splitlines():
            s = line.strip()
            if s and s.lower() != 'serialnumber':
                return hashlib.sha256(s.encode()).hexdigest()
    except Exception:
        pass
    return hashlib.sha256(platform.node().encode()).hexdigest()


def make_license_hash(machine_id, auth_code):
    """license 文件内容：sha256(machine_id + auth_code)"""
    return hashlib.sha256((machine_id + auth_code).encode()).hexdigest()


def verify_license():
    """返回 True 表示已授权，False 需弹出授权对话框"""
    if not os.path.exists(LICENSE_FILE):
        return False
    try:
        with open(LICENSE_FILE, 'r') as f:
            stored = f.read().strip()
        expected = make_license_hash(get_machine_id(), AUTH_CODE)
        return stored == expected
    except Exception:
        return False


def save_license():
    """保存授权文件"""
    os.makedirs(LICENSE_DIR, exist_ok=True)
    h = make_license_hash(get_machine_id(), AUTH_CODE)
    with open(LICENSE_FILE, 'w') as f:
        f.write(h)
    # 隐藏文件
    try:
        ctypes.windll.kernel32.SetFileAttributesW(LICENSE_FILE, 2)  # FILE_ATTRIBUTE_HIDDEN
    except Exception:
        pass


class AuthDialog(QDialog):
    """授权码输入对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('授权验证')
        self.setFixedSize(1120, 680)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet('QDialog { background-color: #ffffff; }')

        layout = QVBoxLayout(self)
        layout.setSpacing(32)
        layout.setContentsMargins(100, 72, 100, 60)

        layout.addStretch()

        icon = QLabel('🔑')
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet('font-size: 72px;')
        layout.addWidget(icon)

        title = QLabel('软件授权验证')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            'font-size: 38px; font-weight: 800; color: #1e293b; letter-spacing: 6px;'
        )
        layout.addWidget(title)

        hint = QLabel('请输入授权码以继续使用')
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet('font-size: 20px; color: #94a3b8;')
        layout.addWidget(hint)

        self._input = QLineEdit()
        self._input.setPlaceholderText('输入授权码...')
        self._input.setMaxLength(32)
        self._input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #e2e8f0; border-radius: 10px;
                padding: 14px 20px; font-size: 50px;
                background-color: #f8fafc; color: #1e293b;
                letter-spacing: 4px;
            }
            QLineEdit:focus { border-color: #3b82f6; background-color: #ffffff; }
        """)
        layout.addWidget(self._input)

        self._btn = QPushButton('验证授权')
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.setFixedHeight(64)
        self._btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white;
                border: none; border-radius: 12px;
                font-size: 22px; font-weight: 700; letter-spacing: 4px;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        self._btn.clicked.connect(self._check)
        layout.addWidget(self._btn)

        self._msg = QLabel('')
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setStyleSheet('font-size: 18px;')
        layout.addWidget(self._msg)

        layout.addStretch()

        self._input.returnPressed.connect(self._check)
        self._input.setFocus()

    def _check(self):
        code = self._input.text().strip()
        if code == AUTH_CODE:
            save_license()
            self.accept()
        else:
            self._msg.setText('授权码错误，请重试')
            self._msg.setStyleSheet('color: #ef4444; font-size: 18px;')
            self._input.clear()
            self._input.setFocus()


@contextlib.contextmanager
def _suppress_stderr():
    try:
        _stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        yield
    finally:
        sys.stderr.close()
        sys.stderr = _stderr


# ==================== 摄像头检测 ====================
class CameraDetector:

    @staticmethod
    def get_available_cameras():
        cameras = []
        for idx in range(8):
            with _suppress_stderr():
                cap = cv2.VideoCapture(idx, CAMERA_BACKEND)
                ok = cap.isOpened()
                if ok:
                    ret, _ = cap.read()
                    if ret:
                        cameras.append(idx)
                cap.release()
            if not ok:
                cap.release()
        return cameras

    @staticmethod
    def get_camera_label(index):
        tail = '(通常是内置摄像头)' if index == 0 else '(可能是USB外置摄像头)'
        return '摄像头 {} {}'.format(index, tail)


# ==================== 摄像头悬浮窗 ====================
class CameraOverlay(QFrame):

    def __init__(self, camera_index=0, overlay_size=(320, 240)):
        super().__init__(None)
        self.camera_index = camera_index
        self._drag_start_pos = None
        self._cap = None
        self._paused = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setMinimumSize(120, 90)
        self.setFixedSize(overlay_size[0], overlay_size[1])
        self._setup_ui()
        self._init_camera()
        self._place_top_right()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)
        self._timer.start(33)

    def _setup_ui(self):
        self.setObjectName('cameraOverlay')
        self.setStyleSheet("""
            #cameraOverlay {
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
        """)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        self._cam_view = QLabel()
        self._cam_view.setAlignment(Qt.AlignCenter)
        self._cam_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._cam_view.setStyleSheet('background-color: #000000;')
        self._cam_view.setMouseTracking(True)
        self._cam_view.installEventFilter(self)
        self._layout.addWidget(self._cam_view)

    def _init_camera(self):
        try:
            if self._cap is not None and self._cap.isOpened():
                self._cap.release()
        except Exception:
            pass
        self._cap = None
        try:
            with _suppress_stderr():
                self._cap = cv2.VideoCapture(self.camera_index, CAMERA_BACKEND)
            if self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        except Exception:
            self._cap = None

    def _place_top_right(self):
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(g.right() - self.width() - 24, g.top() + 24)

    def _update_frame(self):
        if self._paused:
            return
        if self._cap is None or not self._cap.isOpened():
            return
        try:
            ret, frame = self._cap.read()
            if not ret or frame is None:
                return
            frame = cv2.flip(frame, 1)
            lw = self._cam_view.width()
            lh = self._cam_view.height()
            if lw <= 4 or lh <= 4:
                return
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (lw, lh), interpolation=cv2.INTER_LINEAR)
            frame = np.ascontiguousarray(frame)
            h, w, ch = frame.shape
            qi = QImage(frame.data, w, h, w * ch, QImage.Format_RGB888).copy()
            self._cam_view.setPixmap(QPixmap.fromImage(qi))
        except Exception:
            pass

    def eventFilter(self, obj, e):
        if obj is self._cam_view:
            if e.type() == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
                self._drag_start_pos = e.globalPos() - self.frameGeometry().topLeft()
                return True
            elif e.type() == QEvent.MouseMove and self._drag_start_pos is not None:
                self.move(e.globalPos() - self._drag_start_pos)
                return True
            elif e.type() == QEvent.MouseButtonRelease:
                self._drag_start_pos = None
                return True
        return super().eventFilter(obj, e)

    def toggle_visibility(self):
        self.setVisible(not self.isVisible())

    def set_paused(self, paused):
        self._paused = paused
        if paused:
            self._timer.stop()
            blur = QGraphicsBlurEffect(self._cam_view)
            blur.setBlurRadius(14)
            blur.setBlurHints(QGraphicsBlurEffect.PerformanceHint)
            self._cam_view.setGraphicsEffect(blur)
        else:
            self._cam_view.setGraphicsEffect(None)
            if not self._timer.isActive():
                self._timer.start(33)

    def release(self):
        self._timer.stop()
        if self._cap is not None:
            try:
                if self._cap.isOpened():
                    self._cap.release()
            except Exception:
                pass
            self._cap = None

    def closeEvent(self, e):
        self.release()
        super().closeEvent(e)


# ==================== 全屏播放器 ====================
class FullScreenPlayer(QMainWindow):

    def __init__(self, video_path, camera_index=0, overlay_size=(320, 240),
                 on_close=None):
        super().__init__()
        self._video_path = video_path
        self._camera_index = camera_index
        self._on_close = on_close
        self._overlay_size = overlay_size
        self._camera_overlay = None
        self._use_opencv = False
        self._cap = None
        self._video_timer = None
        self._fps = 30.0
        self._total_frames = 0
        self._paused = False
        self._init_done = False

        self.setWindowTitle('视频连线')
        self._setup_ui()
        self._try_play()

    def _setup_ui(self):
        self.setStyleSheet('background-color: #000000;')
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._video_widget = QVideoWidget()
        self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stack.addWidget(self._video_widget)

        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._stack.addWidget(self._video_label)

        # ---------- 暂停模糊遮罩 ----------
        self._pause_overlay = QWidget(self)
        self._pause_overlay.setObjectName('pauseOverlay')
        self._pause_overlay.setStyleSheet(
            '#pauseOverlay { background-color: rgba(0,0,0,100); }'
        )
        self._pause_overlay.hide()

        self._pause_bg = QLabel(self._pause_overlay)
        self._pause_bg.setAlignment(Qt.AlignCenter)
        self._pause_bg.setScaledContents(True)

        self._spinner_label = QLabel(self._pause_overlay)
        self._spinner_label.setAlignment(Qt.AlignCenter)
        self._spinner_label.setFixedSize(120, 120)

        self._pause_text = QLabel('加载中...', self._pause_overlay)
        self._pause_text.setAlignment(Qt.AlignCenter)
        self._pause_text.setStyleSheet(
            'color: #cccccc; font-size: 18px; font-weight: 600;'
            'background: transparent;'
        )

        self._spinner_angle = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._spin)
        self._spinner_timer.setInterval(40)

    # ========== 播放引擎 ==========
    def _try_play(self):
        self._player = QMediaPlayer(self)
        self._player.setVideoOutput(self._video_widget)
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(self._video_path)))
        self._player.error.connect(self._on_qt_error)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.play()

        self._fallback_timer = QTimer(self)
        self._fallback_timer.setSingleShot(True)
        self._fallback_timer.timeout.connect(self._try_opencv_fallback)
        self._fallback_timer.start(800)

    def _on_media_status(self, status):
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia,
                       QMediaPlayer.BufferingMedia):
            try:
                self._fallback_timer.stop()
            except Exception:
                pass
            if not self._init_done:
                self._init_done = True
                self._camera_overlay = CameraOverlay(
                    self._camera_index, self._overlay_size
                )
                self.showFullScreen()
                self._camera_overlay.show()
        elif status == QMediaPlayer.EndOfMedia:
            self._player.setPosition(0)
            self._player.play()

    def _on_qt_error(self, error):
        try:
            self._fallback_timer.stop()
        except Exception:
            pass
        self._fallback_timer.deleteLater()
        self._switch_to_opencv()

    def _try_opencv_fallback(self):
        if self._player.state() == QMediaPlayer.StoppedState:
            self._switch_to_opencv()

    def _switch_to_opencv(self):
        self._use_opencv = True
        try:
            self._player.stop()
        except Exception:
            pass

        self._cap = cv2.VideoCapture(self._video_path)
        if not self._cap.isOpened():
            QMessageBox.critical(self, '无法播放',
                                 '无法打开：\n{}'.format(self._video_path))
            self.close()
            return

        self._fps = self._cap.get(cv2.CAP_PROP_FPS)
        if self._fps <= 0 or self._fps > 120:
            self._fps = 30.0
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))

        self._stack.setCurrentWidget(self._video_label)

        frame_delay = max(10, int(1000.0 / self._fps))
        self._video_timer = QTimer(self)
        self._video_timer.timeout.connect(self._update_opencv_frame)
        self._video_timer.start(frame_delay)

        self._camera_overlay = CameraOverlay(self._camera_index, self._overlay_size)
        self.showFullScreen()
        self._camera_overlay.show()

    def _update_opencv_frame(self):
        if not self._use_opencv or self._paused:
            return
        if self._cap is None or not self._cap.isOpened():
            return
        ret, frame = self._cap.read()
        if not ret:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = self._cap.read()
            if not ret:
                return
        try:
            lw = self._video_label.width()
            lh = self._video_label.height()
            if lw <= 0 or lh <= 0:
                return
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (lw, lh), interpolation=cv2.INTER_LINEAR)
            frame = np.ascontiguousarray(frame)
            h, w, ch = frame.shape
            qi = QImage(frame.data, w, h, w * ch, QImage.Format_RGB888).copy()
            self._video_label.setPixmap(QPixmap.fromImage(qi))
        except Exception:
            pass

    # ========== 控制 ==========
    def _toggle_pause(self):
        was_paused = self._is_currently_paused()
        should_pause = not was_paused

        if self._use_opencv:
            self._paused = should_pause
        else:
            if should_pause:
                self._player.pause()
            else:
                self._player.play()

        if should_pause:
            self._show_pause_overlay()
            if self._camera_overlay is not None:
                self._camera_overlay.set_paused(True)
        else:
            self._hide_pause_overlay()
            if self._camera_overlay is not None:
                self._camera_overlay.set_paused(False)

    def _is_currently_paused(self):
        if self._use_opencv:
            return self._paused
        return self._player.state() != QMediaPlayer.PlayingState

    def _show_pause_overlay(self):
        # 截取当前画面 → 缩小 → 高斯模糊 → 放大（大幅提升性能）
        pix = self.grab()
        scale = 4
        sw, sh = max(1, pix.width() // scale), max(1, pix.height() // scale)
        small = pix.scaled(sw, sh, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        img = small.toImage().convertToFormat(QImage.Format_RGB888)
        ptr = img.bits()
        ptr.setsize(img.byteCount())
        arr = np.array(ptr).reshape(img.height(), img.width(), 3)
        blurred = cv2.GaussianBlur(arr, (21, 21), 0)
        h, w, ch = blurred.shape
        qi = QImage(blurred.data, w, h, w * ch, QImage.Format_RGB888).copy()
        final = QPixmap.fromImage(qi).scaled(
            self.width(), self.height(),
            Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        self._pause_bg.setPixmap(final)
        self._pause_bg.setGeometry(0, 0, self.width(), self.height())

        self._pause_overlay.setGeometry(0, 0, self.width(), self.height())

        cx = (self.width() - 120) // 2
        cy = (self.height() - 160) // 2
        self._spinner_label.move(cx, cy)
        self._pause_text.setGeometry(0, cy + 130, self.width(), 30)

        self._spinner_angle = 0
        self._spinner_timer.start()
        self._pause_overlay.show()
        self._pause_overlay.raise_()

    def _hide_pause_overlay(self):
        self._spinner_timer.stop()
        self._pause_overlay.hide()

    def _spin(self):
        self._spinner_angle = (self._spinner_angle + 12) % 360
        pix = QPixmap(120, 120)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        pen = p.pen()
        pen.setWidth(7)
        pen.setColor(QColor(200, 200, 200, 80))
        p.setPen(pen)
        p.drawArc(10, 10, 100, 100, 0, 360 * 16)
        pen.setColor(QColor(255, 255, 255, 240))
        p.setPen(pen)
        p.drawArc(10, 10, 100, 100, self._spinner_angle * 16, 100 * 16)
        p.end()
        self._spinner_label.setPixmap(pix)

    def _toggle_camera(self):
        if self._camera_overlay is not None:
            self._camera_overlay.toggle_visibility()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()
        elif e.key() == Qt.Key_Space:
            self._toggle_pause()
        elif e.key() == Qt.Key_C:
            self._toggle_camera()
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._pause_overlay.isVisible():
            self._pause_overlay.setGeometry(0, 0, self.width(), self.height())
            self._pause_bg.setGeometry(0, 0, self.width(), self.height())
            cx = (self.width() - 120) // 2
            cy = (self.height() - 160) // 2
            self._spinner_label.move(cx, cy)
            self._pause_text.setGeometry(0, cy + 130, self.width(), 30)

    def closeEvent(self, e):
        if self._video_timer is not None:
            self._video_timer.stop()
        if hasattr(self, '_spinner_timer'):
            self._spinner_timer.stop()
        if self._camera_overlay is not None:
            self._camera_overlay.release()
            self._camera_overlay.close()
        if self._cap is not None:
            try:
                if self._cap.isOpened():
                    self._cap.release()
            except Exception:
                pass
            self._cap = None
        if hasattr(self, '_player'):
            try:
                self._player.stop()
            except Exception:
                pass
        if self._on_close is not None:
            self._on_close()
        super().closeEvent(e)


# ==================== 主界面（明亮系·大幅面） ====================
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('视频连线')
        self.setFixedSize(1680, 1320)
        self._selected_video = None
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet('QMainWindow { background-color: #f0f2f5; }')

        central = QWidget()
        central.setStyleSheet('background: transparent;')
        self.setCentralWidget(central)

        wrap = QVBoxLayout(central)
        wrap.setSpacing(28)
        wrap.setContentsMargins(140, 60, 140, 56)

        # ---------- 标题区 ----------
        title_area = QVBoxLayout()
        title_area.setSpacing(10)

        title = QLabel('视频连线')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            'font-size: 52px; font-weight: 900; color: #1e293b;'
            'letter-spacing: 12px;'
        )
        title_area.addWidget(title)

        sub = QLabel('全屏视频播放  ·  摄像头画中画')
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet('font-size: 18px; color: #94a3b8;')
        title_area.addWidget(sub)

        deauth = QPushButton('退出授权')
        deauth.setCursor(Qt.PointingHandCursor)
        deauth.setFlat(True)
        deauth.setStyleSheet("""
            QPushButton {
                color: #cbd5e1; font-size: 12px; font-weight: 400;
                border: none; background: transparent;
                text-decoration: underline;
            }
            QPushButton:hover { color: #ef4444; }
        """)
        deauth.clicked.connect(self._deauthorize)
        title_area.addWidget(deauth, alignment=Qt.AlignCenter)

        wrap.addLayout(title_area)
        wrap.addSpacing(12)

        # ---------- 视频选择区（大） ----------
        vcard = self._card()
        vl = QVBoxLayout(vcard)
        vl.setContentsMargins(36, 36, 36, 32)
        vl.setSpacing(20)

        self._video_path_label = QLabel('点击下方按钮选择视频文件')
        self._video_path_label.setAlignment(Qt.AlignCenter)
        self._video_path_label.setWordWrap(True)
        self._video_path_label.setMinimumHeight(240)
        self._video_path_label.setStyleSheet("""
            color: #94a3b8; font-size: 22px;
            border: 3px dashed #cbd5e1; border-radius: 16px;
            padding: 48px; background-color: #f8fafc;
        """)
        vl.addWidget(self._video_path_label)

        # 按钮行
        br = QHBoxLayout()
        br.setSpacing(20)
        br.addStretch()

        self._select_btn = QPushButton('浏览文件')
        self._select_btn.setCursor(Qt.PointingHandCursor)
        self._select_btn.setFixedSize(200, 56)
        self._select_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white;
                border: none; border-radius: 12px;
                font-size: 18px; font-weight: 700;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
        """)
        self._select_btn.clicked.connect(self._select_video)
        br.addWidget(self._select_btn)

        self._clear_btn = QPushButton('清除')
        self._clear_btn.setCursor(Qt.PointingHandCursor)
        self._clear_btn.setFixedSize(160, 56)
        self._clear_btn.setEnabled(False)
        self._clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #64748b;
                border: 2px solid #e2e8f0; border-radius: 12px;
                font-size: 17px; font-weight: 600;
            }
            QPushButton:hover {
                background-color: #f1f5f9; color: #334155;
                border-color: #94a3b8;
            }
            QPushButton:disabled {
                background-color: #f8fafc; color: #cbd5e1;
                border-color: #e2e8f0;
            }
        """)
        self._clear_btn.clicked.connect(self._clear_video)
        br.addWidget(self._clear_btn)

        br.addStretch()
        vl.addLayout(br)
        wrap.addWidget(vcard)

        # ---------- 设置区：摄像头 + 画中画 + 开始 ----------
        srow = QHBoxLayout()
        srow.setSpacing(24)

        # 摄像头卡片
        ccard = self._card()
        cl = QVBoxLayout(ccard)
        cl.setContentsMargins(24, 24, 24, 20)
        cl.setSpacing(16)

        ctitle = QLabel('选择摄像头')
        ctitle.setStyleSheet(
            'color: #334155; font-size: 18px; font-weight: 700;'
            'padding-bottom: 4px;'
        )
        cl.addWidget(ctitle)

        crow = QHBoxLayout()
        crow.setSpacing(12)

        self._camera_combo = QComboBox()
        self._camera_combo.setCursor(Qt.PointingHandCursor)
        self._camera_combo.setStyleSheet(self._combo_css())
        crow.addWidget(self._camera_combo, 1)

        rbtn = QPushButton('刷新')
        rbtn.setCursor(Qt.PointingHandCursor)
        rbtn.setFixedSize(64, 44)
        rbtn.setStyleSheet("""
            QPushButton {
                background-color: #f1f5f9; color: #475569;
                border: 1px solid #e2e8f0; border-radius: 10px;
                font-size: 14px; font-weight: 600;
            }
            QPushButton:hover {
                background-color: #e2e8f0; color: #1e293b;
            }
        """)
        rbtn.clicked.connect(self._detect_cameras)
        crow.addWidget(rbtn)
        cl.addLayout(crow)
        srow.addWidget(ccard, 6)

        # 画中画卡片
        scard = self._card()
        sl = QVBoxLayout(scard)
        sl.setContentsMargins(24, 24, 24, 20)
        sl.setSpacing(16)

        stitle = QLabel('画中画大小')
        stitle.setStyleSheet(
            'color: #334155; font-size: 18px; font-weight: 700;'
            'padding-bottom: 4px;'
        )
        sl.addWidget(stitle)

        self._size_combo = QComboBox()
        self._size_combo.setCursor(Qt.PointingHandCursor)
        self._size_combo.setStyleSheet(self._combo_css())
        for name in OVERLAY_SIZES:
            self._size_combo.addItem(name)
        self._size_combo.setCurrentText(DEFAULT_OVERLAY_SIZE)
        sl.addWidget(self._size_combo)

        srow.addWidget(scard, 4)

        # 开始按钮卡片
        btn_card = self._card()
        bl = QVBoxLayout(btn_card)
        bl.setContentsMargins(24, 24, 24, 20)
        bl.setSpacing(16)

        btitle = QLabel('开始连线')
        btitle.setStyleSheet(
            'color: #334155; font-size: 18px; font-weight: 700;'
            'padding-bottom: 4px;'
        )
        bl.addWidget(btitle)

        self._start_btn = QPushButton('开始连线')
        self._start_btn.setEnabled(False)
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setFixedHeight(52)
        self._start_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b82f6; color: white;
                border: none; border-radius: 12px;
                font-size: 20px; font-weight: 700; letter-spacing: 6px;
            }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:pressed { background-color: #1d4ed8; }
            QPushButton:disabled {
                background-color: #e2e8f0; color: #94a3b8;
            }
        """)
        self._start_btn.clicked.connect(self._start_playback)
        bl.addWidget(self._start_btn)

        srow.addWidget(btn_card, 3)

        wrap.addLayout(srow)

        wrap.addStretch()

        # ---------- 底部 ----------
        self._status_label = QLabel('请选择视频文件')
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet('color: #94a3b8; font-size: 16px;')
        wrap.addWidget(self._status_label)

        tips = QLabel('播放时：Space 暂停 / 播放    C 切换摄像头    Esc 退出')
        tips.setAlignment(Qt.AlignCenter)
        tips.setStyleSheet('color: #cbd5e1; font-size: 14px;')
        wrap.addWidget(tips)

        self._detect_cameras()

    # ---------- 控件工厂 ----------
    def _card(self):
        c = QFrame()
        c.setObjectName('card')
        c.setStyleSheet("""
            #card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
        """)
        return c

    def _combo_css(self):
        return """
            QComboBox {
                background-color: #f8fafc; color: #334155;
                border: 1px solid #e2e8f0; border-radius: 10px;
                padding: 10px 18px; font-size: 16px;
            }
            QComboBox:hover { border-color: #3b82f6; }
            QComboBox::drop-down { border: none; width: 32px; }
            QComboBox QAbstractItemView {
                background-color: #ffffff; color: #334155;
                border: 1px solid #e2e8f0; border-radius: 8px;
                selection-background-color: #3b82f6;
                selection-color: white; outline: none;
                padding: 6px; font-size: 15px;
            }
        """

    # ---------- 摄像头 ----------
    def _detect_cameras(self):
        self._camera_combo.clear()
        cameras = CameraDetector.get_available_cameras()
        if not cameras:
            self._camera_combo.addItem('未检测到摄像头', -1)
            self._status_label.setText('未检测到摄像头，请检查设备连接')
            self._status_label.setStyleSheet('color: #ef4444; font-size: 16px;')
        else:
            for idx in cameras:
                self._camera_combo.addItem(CameraDetector.get_camera_label(idx), idx)
            self._status_label.setText(
                '已检测到 {} 个可用摄像头'.format(len(cameras))
            )
            self._status_label.setStyleSheet('color: #10b981; font-size: 16px;')

    # ---------- 视频 ----------
    def _select_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择视频文件', '',
            '视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.ts);;'
            '所有文件 (*.*)'
        )
        if path:
            self._apply_video(path)

    def _apply_video(self, path):
        self._selected_video = path
        name = os.path.basename(path)
        self._video_path_label.setText(name)
        self._video_path_label.setStyleSheet("""
            color: #1e40af; font-size: 28px; font-weight: 700;
            border: 3px solid #3b82f6; border-radius: 16px;
            padding: 48px; background-color: #eff6ff;
        """)
        self._start_btn.setEnabled(True)
        self._clear_btn.setEnabled(True)
        self._status_label.setText('就绪')
        self._status_label.setStyleSheet('color: #10b981; font-size: 16px;')

    def _clear_video(self):
        self._selected_video = None
        self._video_path_label.setText('点击下方按钮选择视频文件')
        self._video_path_label.setStyleSheet("""
            color: #94a3b8; font-size: 22px;
            border: 3px dashed #cbd5e1; border-radius: 16px;
            padding: 48px; background-color: #f8fafc;
        """)
        self._start_btn.setEnabled(False)
        self._clear_btn.setEnabled(False)
        self._status_label.setText('请选择视频文件')
        self._status_label.setStyleSheet('color: #94a3b8; font-size: 16px;')

    # ---------- 播放 ----------
    def _start_playback(self):
        if not self._selected_video:
            return
        cam_idx = self._camera_combo.currentData()
        if cam_idx is None or cam_idx < 0:
            QMessageBox.warning(self, '提示', '请先选择可用的摄像头！')
            return

        sn = self._size_combo.currentText()
        ov_size = OVERLAY_SIZES.get(sn, OVERLAY_SIZES[DEFAULT_OVERLAY_SIZE])

        self.hide()
        self._player = FullScreenPlayer(
            self._selected_video, cam_idx, ov_size,
            on_close=self._on_player_closed
        )

    def _on_player_closed(self):
        self.show()
        self._detect_cameras()

    def _deauthorize(self):
        reply = QMessageBox.question(
            self, '退出授权',
            '退出授权后下次启动需要重新输入授权码，确定继续？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            clear_license()
            QMessageBox.information(self, '提示', '已退出授权，重启软件后需重新验证。')


# ==================== 入口 ====================
def main():
    # 1. 单实例检查
    if not check_single_instance():
        ctypes.windll.user32.MessageBoxW(
            0, '程序已在运行中，不能同时打开多个实例。', '视频连线', 0x30
        )
        sys.exit(0)

    # 2. Qt 平台插件路径
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(base, 'platforms')
    else:
        qt_dir = os.path.dirname(PyQt5.__file__)
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = os.path.join(
            qt_dir, 'Qt5', 'plugins', 'platforms'
        )

    app = QApplication(sys.argv)
    app.setApplicationName('视频连线')
    app.setStyle('Fusion')
    app.setFont(QFont('Microsoft YaHei', 10))

    # 3. 授权验证
    if not verify_license():
        dlg = AuthDialog()
        if dlg.exec_() != QDialog.Accepted:
            sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
