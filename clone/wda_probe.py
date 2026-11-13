# -*- coding: utf-8 -*-
"""验证：浮窗是否真的「截图截不到」。

对照法：窗口出现前先截一次该区域（桌面/背后的窗口），窗口出现后再截同区域。
WDA 生效 → 两张几乎一样（窗口没进画面）；WDA 失效 → 第二张会变成我们的深色面板。
注意：SetWindowDisplayAffinity 只能由窗口所属进程设置，跨进程调用会失败，
所以这里不做「关保护」的对照，而是用「窗口出现前/后」做对照。
"""
import ctypes
import io
import os
import subprocess
import sys
import time
from ctypes import wintypes

from PIL import ImageChops, ImageGrab, ImageStat

LOG = io.StringIO()


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")


user32 = ctypes.windll.user32
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_window(pid, title="Settings"):
    hits = []

    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        n = user32.GetWindowTextLengthW(h)
        if not n:
            return True
        b = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, b, n + 1)
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and b.value == title:
            hits.append(h)
        return True

    user32.EnumWindows(CB(cb), 0)
    return hits[0] if hits else None


def rect_of(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def stat_msg(im):
    st = ImageStat.Stat(im.convert("L"))
    return f"mean={st.mean[0]:.1f} stddev={st.stddev[0]:.1f}"


def main():
    bbox = (835, 40, 1495, 440)  # 主屏右上角默认位置，窗口起来后会用实际 rect 覆盖
    before = ImageGrab.grab(all_screens=True)
    env = dict(os.environ, MODE="exam", PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([sys.executable, "mvp.py"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        hwnd = None
        for _ in range(60):
            time.sleep(0.5)
            hwnd = find_window(p.pid)
            if hwnd:
                break
        if not hwnd:
            log("FAIL 没找到 Settings 窗口")
            return 2
        bbox = rect_of(hwnd)
        log("hwnd", hwnd, "rect", bbox, "visible", bool(user32.IsWindowVisible(hwnd)))
        time.sleep(1.5)
        after = ImageGrab.grab(all_screens=True)
        a = before.crop(bbox).convert("RGB")
        b = after.crop(bbox).convert("RGB")
        a.save("wda_before.png")
        b.save("wda_after.png")
        log("窗口出现前：", stat_msg(a))
        log("窗口出现后：", stat_msg(b))
        diff = ImageChops.difference(a, b)
        st = ImageStat.Stat(diff)
        changed = st.mean[0]
        log(f"像素差 mean={changed:.2f} max={max(st.extrema[0]) if hasattr(st,'extrema') else '?'}")
        if changed < 2:
            log("PASS 截图里看不到浮窗（WDA 生效）")
        else:
            log("WARN 截图能看到变化，检查是否被别的窗口盖住/遮挡")
        return 0
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:
            p.kill()
        open("wda_probe.log", "w", encoding="utf-8").write(LOG.getvalue())


if __name__ == "__main__":
    sys.exit(main())
