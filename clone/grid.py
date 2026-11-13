"""图形准备页：全屏网格 + 涂鸦层，帮忙做行测/图形推理题。

用法（笔试时）：
  Ctrl+Alt+G  显示/隐藏
  左键拖动    画线（对照图形旋转/对称/叠加关系）
  右键        清空涂鸦

设计要点：
- `WindowDoesNotAcceptFocus + WA_ShowWithoutActivating`：显示和画线都不抢浏览器焦点，
  不会触发笔试平台的「切屏」判定（鼠标事件仍然能收到）。
- 自身 `SetWindowDisplayAffinity(0x11)`：网格和涂鸦不会出现在录屏/共享里。
- 不采集、不联网、不写文件。
"""
import ctypes

GRID_PX = 64
GRID_COLOR = (0, 190, 255, 46)
AXIS_COLOR = (0, 255, 180, 90)
PEN_COLOR = (255, 86, 86, 230)
PEN_WIDTH = 3


def _wda(hwnd: int) -> bool:
    try:
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11))
    except Exception:
        return False


class Grid:
    """延迟创建：第一次按 Ctrl+Alt+G 才 import PySide6 并建窗口。"""

    def __init__(self) -> None:
        from PySide6 import QtCore, QtGui, QtWidgets

        self.QtCore, self.QtGui, self.QtWidgets = QtCore, QtGui, QtWidgets
        self.strokes: list[list] = []
        self._cur: list | None = None
        self.visible = False

        self.win = QtWidgets.QWidget()
        self.win.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.Tool
            | QtCore.Qt.WindowDoesNotAcceptFocus
        )
        self.win.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.win.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.win.setWindowTitle("Settings")
        self.win.setMouseTracking(True)

        geo = QtCore.QRect()
        for sc in QtWidgets.QApplication.screens():
            geo = geo.united(sc.geometry())
        self.win.setGeometry(geo)

        self.win.paintEvent = self._paint
        self.win.mousePressEvent = self._press
        self.win.mouseMoveEvent = self._move
        self.win.mouseReleaseEvent = self._release

    # ---- 绘制
    def _paint(self, _ev) -> None:
        QtCore = self.QtCore
        p = self.QtGui.QPainter(self.win)
        p.setRenderHint(self.QtGui.QPainter.Antialiasing, True)
        w, h = self.win.width(), self.win.height()
        # 网格
        pen = self.QtGui.QPen(self.QtGui.QColor(*GRID_COLOR), 1)
        p.setPen(pen)
        x = 0
        while x <= w:
            p.drawLine(x, 0, x, h)
            x += GRID_PX
        y = 0
        while y <= h:
            p.drawLine(0, y, w, y)
            y += GRID_PX
        # 中线
        p.setPen(self.QtGui.QPen(self.QtGui.QColor(*AXIS_COLOR), 1, QtCore.Qt.DashLine))
        p.drawLine(w // 2, 0, w // 2, h)
        p.drawLine(0, h // 2, w, h // 2)
        # 涂鸦
        p.setPen(self.QtGui.QPen(self.QtGui.QColor(*PEN_COLOR), PEN_WIDTH,
                                 QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
        for s in self.strokes:
            if len(s) == 1:
                p.drawPoint(s[0])
                continue
            for a, b in zip(s, s[1:]):
                p.drawLine(a, b)
        p.end()

    # ---- 鼠标
    def _press(self, ev) -> None:
        if ev.button() == self.QtCore.Qt.RightButton:
            self.strokes.clear()
            self._cur = None
            self.win.update()
            return
        self._cur = [self._global(ev)]
        self.strokes.append(self._cur)
        self.win.update()

    def _move(self, ev) -> None:
        if self._cur is not None:
            self._cur.append(self._global(ev))
            self.win.update()

    def _release(self, _ev) -> None:
        self._cur = None

    def _global(self, ev):
        # 画布是全屏虚拟桌面，用窗口内坐标即可（多屏时相对虚拟桌面原点）
        return ev.position().toPoint()

    # ---- 显隐
    def toggle(self) -> bool:
        if self.visible:
            self.win.hide()
            self.visible = False
        else:
            self.strokes.clear()
            self.win.show()
            self.visible = True
            self.win.update()
            _wda(int(self.win.winId()))
        return self.visible
