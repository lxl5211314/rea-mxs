# -*- coding: utf-8 -*-
"""笔试 UI 逻辑自检：题目列表 / 缩略图随题切换 / 重识别替换 / 隐身保活。

不联网、不截屏，只驱动 Overlay 的内存状态。
输出 exam_ui_test.log（utf-8），避免 PowerShell 管道把中文打成乱码。
"""
import io
import os
import sys
import time

LOG = io.StringIO()


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")


os.environ.setdefault("MODE", "exam")
sys.argv = [a for a in sys.argv if a != "--no-ui"]

import mvp  # noqa: E402

from PySide6 import QtCore, QtGui  # noqa: E402

ui = mvp.Overlay()
assert ui.qt and ui.win, "Overlay 未起来（需要图形会话）"

# 造两张白图当截图
def png(w, h):
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor("#ffffff"))
    buf = QtCore.QByteArray()
    b = QtCore.QBuffer(buf)
    b.open(QtCore.QIODevice.WriteOnly)
    pm.save(b, "PNG")
    return bytes(buf)


p1, p2 = png(300, 120), png(280, 140)

# 1) 第一题（截图）+ 答案
ui.begin_answer("（截图）", thumb=p1, kind="shot")
ui.set_answer("答案A：两数之和用哈希表", force=True)
ui.history[-1]["ok"] = True

# 2) 第二题（文本）+ 答案
ui.begin_answer("第二题：TCP 三次握手", kind="text")
ui.set_answer("答案B", force=True)

# 3) 翻到上一题：缩略图应恢复为 p1
ui.nav(-1)
assert ui.idx == 0, ui.idx
assert ui.history[0]["thumb"] == p1
vis1 = ui.thumb.isVisible()
pix = ui.thumb.pixmap()
log(f"NAV idx={ui.idx} thumb_visible={vis1} thumb_w={pix.width()}")

# 4) 翻回第二题：无缩略图 → 应隐藏
ui.nav(1)
vis2 = ui.thumb.isVisible()
log(f"NAV idx={ui.idx} thumb_visible={vis2}")
assert vis2 is False

# 5) 题目列表开/关
ui.show_list()
txt_list = ui.view.toPlainText()
assert "题目列表（2）" in txt_list, txt_list[:200]
assert "第二题" in txt_list
log("LIST_OPEN ok")
ui.show_list()
assert "答案B" in ui.view.toPlainText()
log("LIST_CLOSE ok")

# 6) 重识别：replace=True 不新增题目
n0 = len(ui.history)
ui.begin_answer("（截图）", thumb=p2, kind="shot", replace=True)
assert len(ui.history) == n0, len(ui.history)
ui.set_answer("答案B2", force=True)
log(f"RESEND replace ok len={len(ui.history)} idx={ui.idx}")

# 7) 隐身保活：手动跑一次，状态应为 True 或 False（不能抛）
ui._stealth_main()
has_timer = hasattr(ui, "_stealth_timer") and ui._stealth_timer.isActive()
log(f"STEALTH state={ui._stealth_state} timer={has_timer}")

# 7b) Shift+方向键移动窗口：每次 20px
x0, y0 = ui.win.pos().x(), ui.win.pos().y()
ui.move_by(-20, 0)
ui.move_by(0, 20)
dx, dy = ui.win.pos().x() - x0, ui.win.pos().y() - y0
assert dx == -20 and dy == 20, (dx, dy)
log(f"MOVE dx={dx} dy={dy}")

# 8) 列表里应显示每题状态
ui.show_list()
t = ui.view.toPlainText()
assert "字]" in t or "字）" in t, t[:200]
log("LIST_STATE ok")

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exam_ui_test.log"),
     "w", encoding="utf-8").write(LOG.getvalue())
print("EXAM_UI_OK", flush=True)
ui.quit()
