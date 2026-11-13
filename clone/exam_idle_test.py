# -*- coding: utf-8 -*-
"""笔试常驻窗验证：
1) 空闲卡片显示快捷键、窗口可见；
2) 截图前 grab_hide() 隐身、grab_show() 恢复；
3) 幽灵模式下 grab_show() 不会把隐藏的窗口叫出来。
用法：python exam_idle_test.py [ghost]
"""
import os
import sys
import time

mode = "ghost" if "ghost" in sys.argv else "idle"
os.environ["MODE"] = "exam"
os.environ["EXAM_GHOST"] = "1" if mode == "ghost" else "0"
os.environ["EXAM_IDLE"] = "1"

from PIL import ImageGrab, ImageStat  # noqa: E402

import mvp  # noqa: E402

ui = mvp.Overlay()
assert ui.qt, "Qt 初始化失败"


def pump(sec=0.4):
    end = time.time() + sec
    while time.time() < end:
        ui.app.processEvents()
        time.sleep(0.02)


def brightness():
    g = ui.win.frameGeometry()
    img = ImageGrab.grab(bbox=(g.x(), g.y(), g.x() + g.width(), g.y() + g.height()), all_screens=True)
    return round(ImageStat.Stat(img.convert("L")).mean[0], 1)


if mode == "idle":
    ui.set_status_wrap(mvp.EXAM_IDLE_HELP)
    ui.show()
    pump(0.8)
    text = ui.view.toPlainText()
    print("visible_idle=", ui.win.isVisible())
    print("card_has_keys=", ("Ctrl+Shift+S" in text and "Shift+Alt+双击" in text))
    b1 = brightness()
    ui.grab_hide()
    hidden_now = not ui.win.isVisible()
    pump(0.3)
    b2 = brightness()
    ui.grab_show()
    pump(0.4)
    print(f"hidden_during_grab={hidden_now} brightness visible={b1} hidden={b2}")
    print("restored_visible=", ui.win.isVisible())
    ok = (hidden_now and ui.win.isVisible() and "Ctrl+Shift+S" in text)
    print("EXAM_IDLE_OK" if ok else "EXAM_IDLE_FAIL")
else:
    ui.hide()
    pump(0.4)
    print("ghost_start_visible=", ui.win.isVisible())
    ui.grab_hide()   # 真实流程：每次截图前都会先 hide
    ui.grab_show()
    pump(0.4)
    print("ghost_after_shot_visible=", ui.win.isVisible())
    print("EXAM_GHOST_HIDE_OK" if not ui.win.isVisible() else "EXAM_GHOST_HIDE_FAIL")

ui.app.quit()
