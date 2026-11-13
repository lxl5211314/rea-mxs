# -*- coding: utf-8 -*-
"""真机回归：从工作线程走完整截图链路（grab_hide → 抓图 → grab_show）。

复现用户遇到的 0xC000041D：钩子线程里直接 win.hide() + processEvents()。
用法：python shot_thread_test.py
"""
import os
import threading
import time

os.environ["MODE"] = "exam"
os.environ["EXAM_GHOST"] = "0"
os.environ["EXAM_IDLE"] = "1"
os.environ["LLM_WARM"] = "0"

import mvp  # noqa: E402
from shot import Screenshotter  # noqa: E402

ui = mvp.Overlay()
assert ui.qt
ui.set_status_wrap(mvp.EXAM_IDLE_HELP)
ui.show()

state = {}


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        ui.app.processEvents()
        time.sleep(0.01)


def on_shot(png, cancel):
    state["hidden_during_llm"] = not ui.win.isVisible()
    state["png_kb"] = len(png) // 1024
    time.sleep(0.25)
    ui.begin_answer("（截图）")
    ui.set_answer("测试答案：线程安全", force=True)
    state["answered"] = True


s = Screenshotter(on_shot, ui.set_status,
                  before_grab=ui.grab_hide, after_grab=ui.grab_show)

pump(0.8)
state["start_visible"] = ui.win.isVisible()


def worker():
    t0 = time.time()
    s.trigger("full")
    state["trigger_cost"] = round(time.time() - t0, 3)


th = threading.Thread(target=worker, daemon=True)
th.start()
end = time.time() + 6
while time.time() < end and th.is_alive():
    ui.app.processEvents()
    time.sleep(0.01)
pump(2.0)

state["restored"] = ui.win.isVisible()
state["alive"] = True
print(state)
ok = (state.get("start_visible") and state.get("hidden_during_llm")
      and state.get("restored") and state.get("answered"))
print("SHOT_THREAD_OK" if ok else "SHOT_THREAD_FAIL")
ui.app.quit()
