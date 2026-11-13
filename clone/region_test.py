"""框选截图自检：模拟一次拖拽，校验回调收到的全局坐标。"""
import os
import sys

os.environ.setdefault("MODE", "exam")

from PySide6 import QtCore, QtTest, QtWidgets  # noqa: E402

import mvp  # noqa: E402

ui = mvp.Overlay()
app = ui.app
got = []
ui.request_region(lambda r: got.append(r))
app.processEvents()

sels = [w for w in app.topLevelWidgets()
        if w is not ui.win and isinstance(w, QtWidgets.QWidget) and w.isVisible()
        and (w.windowFlags() & QtCore.Qt.Tool)]
print("overlay_count", len(sels), flush=True)
if not sels:
    print("PICK_FAIL no overlay", flush=True)
    sys.exit(1)
sel = sels[-1]

QtTest.QTest.mousePress(sel, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(100, 100))
app.processEvents()
QtTest.QTest.mouseMove(sel, QtCore.QPoint(400, 300))
app.processEvents()
QtTest.QTest.mouseRelease(sel, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(400, 300))
app.processEvents()

print("rect", got, flush=True)
if got:
    l, t, r, b = got[0]
    print("size", r - l, b - t, flush=True)
    print("PICK_OK" if (r - l, b - t) == (301, 201) else "PICK_BAD_SIZE", flush=True)
else:
    print("PICK_FAIL no callback", flush=True)
sys.exit(0)
