# -*- coding: utf-8 -*-
"""对照：不透明窗口 vs 半透明窗口，在 GDI 整屏抓图里是否可见；WDA 前后各测一次。"""
import ctypes
import time

from PIL import ImageGrab
from PySide6 import QtCore, QtWidgets

app = QtWidgets.QApplication([])


def make(x, translucent):
    w = QtWidgets.QWidget()
    w.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
    if translucent:
        w.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        w.setStyleSheet("background:rgba(255,0,0,255);border-radius:8px")
    else:
        w.setStyleSheet("background:#ff0000")
    w.setGeometry(x, 120, 200, 150)
    w.show()
    return w


opaque = make(120, False)
alpha = make(360, True)
for _ in range(50):
    app.processEvents()
    time.sleep(0.02)


def probe(tag):
    img = ImageGrab.grab(bbox=(100, 100, 620, 320), all_screens=True)
    a = img.getpixel((120, 120))
    b = img.getpixel((400, 120))
    print(f"{tag}: opaque={a} translucent={b}", flush=True)
    return a, b


probe("no-wda")
for w in (opaque, alpha):
    ok = ctypes.windll.user32.SetWindowDisplayAffinity(int(w.winId()), 0x11)
    print("wda set", w.width(), ok, flush=True)
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
probe("wda-0x11")
for w in (opaque, alpha):
    ctypes.windll.user32.SetWindowDisplayAffinity(int(w.winId()), 0)
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)
probe("wda-off-again")
app.quit()
