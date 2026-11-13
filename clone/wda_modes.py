# -*- coding: utf-8 -*-
"""WDA 模式对照：0 / 1(MONITOR) / 0x11(EXCLUDEFROMCAPTURE) 在 GDI 截图里的表现。"""
import ctypes
import sys
import time

from PIL import ImageGrab, ImageStat
from PySide6 import QtCore, QtWidgets

app = QtWidgets.QApplication(sys.argv)
w = QtWidgets.QWidget()
w.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
w.setStyleSheet("background:#ff0000;")
w.setGeometry(200, 200, 400, 300)
w.show()
app.processEvents()
time.sleep(0.8)

hwnd = int(w.winId())
u = ctypes.windll.user32
bbox = (200, 200, 600, 500)


def shot(tag):
    app.processEvents()
    time.sleep(0.5)
    im = ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")
    m = ImageStat.Stat(im).mean
    red = m[0] > 180 and m[1] < 90
    print(f"{tag}: R={m[0]:.0f} G={m[1]:.0f} B={m[2]:.0f} 红色={red}", flush=True)
    return im


shot("初始(未设)")
for mode, name in ((0, "WDA_NONE"), (1, "WDA_MONITOR"), (0x11, "EXCLUDEFROMCAPTURE")):
    ok = u.SetWindowDisplayAffinity(hwnd, mode)
    im = shot(f"{name} ({mode:#x}) ok={ok}")
    im.save(f"wda_{mode}.png")
w.close()
