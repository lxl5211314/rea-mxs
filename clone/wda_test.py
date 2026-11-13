r"""验证 SetWindowDisplayAffinity 在不同窗口样式下的返回值。

面试侠的 capture_protection 状态里专门有 layeredWindow / win11KernelBug 字段，
说明"透明窗 + 防截屏"确实有坑。这个脚本一次跑三种窗口，告诉你到底哪种能设成功。

  python wda_test.py
"""
from __future__ import annotations

import ctypes
import sys

from PySide6 import QtCore, QtWidgets

WDA_NONE = 0x0
WDA_MONITOR = 0x1
WDA_EXCLUDEFROMCAPTURE = 0x11
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020

u32 = ctypes.windll.user32


def try_wda(win: QtWidgets.QWidget, flag: int) -> tuple[bool, int]:
    hwnd = int(win.winId())
    ok = bool(u32.SetWindowDisplayAffinity(hwnd, flag))
    got = ctypes.c_uint(0)
    read_ok = bool(u32.GetWindowDisplayAffinity(hwnd, ctypes.byref(got)))
    return ok, (got.value if read_ok else -1)


def make(app, translucent: bool, layered: bool) -> QtWidgets.QWidget:
    w = QtWidgets.QWidget()
    w.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
    if translucent:
        w.setAttribute(QtCore.Qt.WA_TranslucentBackground)
    w.resize(300, 120)
    w.move(200, 200)
    w.show()
    app.processEvents()
    if layered:
        hwnd = int(w.winId())
        style = u32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
    app.processEvents()
    return w


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    cases = [
        ("普通无边框置顶窗", False, False),
        ("半透明窗(WA_TranslucentBackground)", True, False),
        ("半透明 + 点击穿透(WS_EX_LAYERED)", True, True),
    ]
    for name, tr, lay in cases:
        w = make(app, tr, lay)
        ok, got = try_wda(w, WDA_EXCLUDEFROMCAPTURE)
        print(f"{name}: SetWDA={ok}  readback=0x{got:X}")
        w.close()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
