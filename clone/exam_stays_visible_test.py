# -*- coding: utf-8 -*-
"""常驻窗验证：答题前后窗口都保持可见；卡片里能直接看到退出方式。"""
import os
import time

os.environ["MODE"] = "exam"
os.environ["EXAM_GHOST"] = "0"
os.environ["EXAM_IDLE"] = "1"
os.environ["GHOST_HIDE_AFTER"] = "2"   # 故意设小：常驻模式下也不该被它藏掉

import mvp  # noqa: E402

ui = mvp.Overlay()
assert ui.qt


def pump(sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        ui.app.processEvents()
        time.sleep(0.02)


ui.set_status_wrap(mvp.EXAM_IDLE_HELP)
ui.show()
pump(0.6)
idle_visible = ui.win.isVisible()
idle_text = ui.view.toPlainText()

ui.begin_answer("（截图）")
ui.set_answer("答案第一行\n答案第二行", force=True)
pump(3.0)   # 超过 GHOST_HIDE_AFTER(2s)，常驻模式不应自动隐藏

after_answer_text = ui.view.toPlainText()
alive = ui.win.isVisible()
ghost_timer = getattr(ui, "_ghost_thread", None)
timer_running = bool(ghost_timer and ghost_timer.is_alive())

print("idle_visible=", idle_visible)
print("has_exit_hint=", ("Ctrl+Shift+Q" in idle_text and "退出" in idle_text))
print("text_rendered=", ("答案第一行" in after_answer_text and "<div" not in after_answer_text))
print("visible_after_3s=", alive, "ghost_timer=", timer_running)
print("EXAM_STAY_OK" if (idle_visible and alive and not timer_running) else "EXAM_STAY_FAIL")
ui.app.quit()
