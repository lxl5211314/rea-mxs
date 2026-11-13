# -*- coding: utf-8 -*-
"""跨线程截图隐身回归测试。

背景：Screenshotter.trigger() 跑在鼠标钩子开出来的工作线程里，
before_grab 直接调 win.hide() 会让 Qt 在原生回调中抛异常，
进程以 0xC000041D（STATUS_FATAL_USER_CALLBACK_EXCEPTION）直接消失。
本测试从工作线程调 grab_hide()/grab_show()，主线程负责 pump 事件。

用法：python grab_thread_test.py
"""
import os
import threading
import time

os.environ["MODE"] = "exam"
os.environ["EXAM_GHOST"] = "0"
os.environ["EXAM_IDLE"] = "1"

import mvp  # noqa: E402

ui = mvp.Overlay()
assert ui.qt, "Qt 初始化失败"
ui.set_status_wrap(mvp.EXAM_IDLE_HELP)
ui.show()

res = {}


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        ui.app.processEvents()
        time.sleep(0.01)


pump(0.6)
print("start_visible=", ui.win.isVisible())


def worker():
    t0 = time.time()
    ui.grab_hide()
    res["hide_cost"] = round(time.time() - t0, 3)
    res["hidden"] = not ui.win.isVisible()
    time.sleep(0.15)
    ui.grab_show()


th = threading.Thread(target=worker, daemon=True)
th.start()

# 主线程持续跑事件循环，模拟 app.exec()
end = time.time() + 3
while time.time() < end and th.is_alive():
    ui.app.processEvents()
    time.sleep(0.01)
pump(0.6)
th.join(2)

res["restored"] = ui.win.isVisible()
res["alive"] = True
print(res)

ok = res.get("hidden") is True and res.get("restored") is True
print("GRAB_THREAD_OK" if ok else "GRAB_THREAD_FAIL")
ui.app.quit()
