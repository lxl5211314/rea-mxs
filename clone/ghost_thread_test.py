# -*- coding: utf-8 -*-
"""验证热键线程调用 toggle_visible 能正确显示/隐藏（跨线程 marshal）。"""
import os
import sys
import threading
import time

os.environ["MODE"] = "exam"
os.environ["EXAM_GHOST"] = "0"
os.environ["GHOST_HIDE_AFTER"] = "30"

import mvp  # noqa: E402

ui = mvp.Overlay()
if not ui.win:
    print("NO_QT", flush=True)
    sys.exit(1)

from PySide6 import QtCore  # noqa: E402

ui.hide()


def pump(ms):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


res = []
threading.Thread(target=ui.toggle_visible, daemon=True).start()
pump(600)
res.append(("thread_toggle_show", ui.win.isVisible()))
threading.Thread(target=ui.toggle_visible, daemon=True).start()
pump(600)
res.append(("thread_toggle_hide", not ui.win.isVisible()))
threading.Thread(target=ui.show, daemon=True).start()
pump(600)
res.append(("thread_show", ui.win.isVisible()))
threading.Thread(target=ui.hide, daemon=True).start()
pump(600)
res.append(("thread_hide", not ui.win.isVisible()))

for k, v in res:
    print(f"{k}={v}", flush=True)
ok = all(v for _, v in res)
print("THREAD_TOGGLE_OK" if ok else "THREAD_TOGGLE_FAIL", flush=True)
open("ghost_thread.log", "w", encoding="utf-8").write("\n".join(f"{k}={v}" for k, v in res) + "\n")
os._exit(0 if ok else 1)
