# -*- coding: utf-8 -*-
"""最小验证：一个纯红窗口 + WDA，看截图里是否出现红色。

红窗放 (200,200)；先不设 WDA 截一张（应看到红），再设 WDA 截一张（应看到桌面）。
同进程内调用 SetWindowDisplayAffinity，避免跨进程失败。
"""
import ctypes
import io
import sys
import time

from PIL import ImageGrab, ImageStat

LOG = io.StringIO()


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")


from PySide6 import QtCore, QtWidgets  # noqa: E402

app = QtWidgets.QApplication(sys.argv)
w = QtWidgets.QWidget()
w.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
w.setStyleSheet("background:#ff0000;")
w.setGeometry(200, 200, 400, 300)
w.show()
app.processEvents()
time.sleep(0.6)

hwnd = int(w.winId())
user32 = ctypes.windll.user32

app.processEvents()
time.sleep(0.3)
im1 = ImageGrab.grab(bbox=(200, 200, 600, 500), all_screens=True).convert("RGB")
m1 = ImageStat.Stat(im1)
log("WDA 未设：R=%.0f G=%.0f B=%.0f" % tuple(m1.mean))

ok = user32.SetWindowDisplayAffinity(hwnd, 0x11)
log("SetWindowDisplayAffinity ->", ok, "err", ctypes.get_last_error())
app.processEvents()
time.sleep(0.5)
im2 = ImageGrab.grab(bbox=(200, 200, 600, 500), all_screens=True).convert("RGB")
m2 = ImageStat.Stat(im2)
log("WDA 已设：R=%.0f G=%.0f B=%.0f" % tuple(m2.mean))
im1.save("wda_ctl_on.png")
im2.save("wda_ctl_off.png")

red1 = m1.mean[0] > 200 and m1.mean[1] < 80
red2 = m2.mean[0] > 200 and m2.mean[1] < 80
log("未设时应为红:", red1, "已设时应不是红:", not red2)
log("RESULT", "PASS 截图截不到（WDA 生效）" if red1 and not red2 else "FAIL")

open("wda_ctl.log", "w", encoding="utf-8").write(LOG.getvalue())
w.close()
