# -*- coding: utf-8 -*-
"""幽灵窗行为测试：默认隐藏 → 答案到达显示 → 超时自动隐藏 → F8 显示后不再自动消失。"""
import os
import sys

os.environ["MODE"] = "exam"
os.environ["EXAM_GHOST"] = "1"
os.environ["GHOST_HIDE_AFTER"] = "2"
import mvp  # noqa: E402

ui = mvp.Overlay()
if not ui.win:
    print("NO_QT", flush=True)
    sys.exit(1)

from PySide6 import QtCore  # noqa: E402

log = []
ui.hide()
log.append(("start_hidden", not ui.win.isVisible()))
ui._render_main("第一段答案")
log.append(("after_answer_visible", ui.win.isVisible()))
log.append(("timer_active", bool(getattr(ui, "_ghost_thread", None))))

loop = QtCore.QEventLoop()


def wait(ms):
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


wait(2600)
log.append(("auto_hidden", not ui.win.isVisible()))

ui.show()
log.append(("manual_show_visible", ui.win.isVisible()))
log.append(("timer_stopped", not (getattr(ui, "_ghost_thread", None) and ui._ghost_thread.is_alive())))
wait(2600)
log.append(("manual_stays_visible", ui.win.isVisible()))

for k, v in log:
    print(f"{k}={v}", flush=True)
ok = all(v for _, v in log)
print("EXAM_GHOST_OK" if ok else "EXAM_GHOST_FAIL", flush=True)
open("ghost_test.log", "w", encoding="utf-8").write("\n".join(f"{k}={v}" for k, v in log) + "\n")
sys.stdout.flush()
os._exit(0 if ok else 1)
