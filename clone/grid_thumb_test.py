# -*- coding: utf-8 -*-
"""grid + 缩略图 离线自检：不联网，纯 Qt 事件模拟。输出 grid_thumb.log (utf-8)。"""
import sys, io, time
sys.path.insert(0, r"E:\aaa_msx\clone")
log = io.StringIO()
def w(s):
    print(s); log.write(s + "\n")

import mvp
ui = mvp.Overlay()
QtCore, QtGui = ui.QtCore, ui.QtGui
from grid import Grid
g = Grid()
vis = g.toggle()
w(f"GRID toggle visible={vis}")
assert vis is True

def mev(t, x, y, btn=QtCore.Qt.LeftButton):
    return QtGui.QMouseEvent(QtCore.QEvent.Type(t), QtCore.QPointF(x, y),
                             QtCore.QPointF(x, y), btn, btn, QtCore.Qt.NoModifier)

g.win.mousePressEvent(mev(QtCore.QEvent.MouseButtonPress, 10, 10))
g.win.mouseMoveEvent(mev(QtCore.QEvent.MouseMove, 40, 50))
g.win.mouseMoveEvent(mev(QtCore.QEvent.MouseMove, 80, 90))
g.win.mouseReleaseEvent(mev(QtCore.QEvent.MouseButtonRelease, 80, 90))
w(f"GRID strokes={len(g.strokes)} len0={len(g.strokes[0]) if g.strokes else 0}")
assert len(g.strokes) == 1 and len(g.strokes[0]) == 3

g.win.mousePressEvent(mev(QtCore.QEvent.MouseButtonPress, 20, 20, QtCore.Qt.RightButton))
g.win.mouseReleaseEvent(mev(QtCore.QEvent.MouseButtonRelease, 20, 20, QtCore.Qt.RightButton))
w(f"GRID after right-click strokes={len(g.strokes)}")
assert len(g.strokes) == 0

vis2 = g.toggle()
w(f"GRID toggle2 visible={vis2}")
assert vis2 is False

# 缩略图
pm = QtGui.QPixmap(320, 120); pm.fill(QtGui.QColor(255, 0, 0))
buf = QtCore.QBuffer(); buf.open(QtCore.QIODevice.WriteOnly)
pm.save(buf, "PNG"); data = bytes(buf.data())
ui.set_thumb(data)
ui.app.processEvents()
w(f"THUMB visible={ui.thumb.isVisible()} pix_null={ui.thumb.pixmap().isNull()}")
assert ui.thumb.isVisible() and not ui.thumb.pixmap().isNull()
pw = ui.thumb.pixmap().width()
w(f"THUMB scaled w={pw}")
assert pw <= 240

ui.app.processEvents()
w("GRID_THUMB_OK")
with open(r"E:\aaa_msx\clone\grid_thumb.log", "w", encoding="utf-8") as f:
    f.write(log.getvalue())
