"""截图 → 视觉模型 → 答案。

四种取图方式（和面试侠一致）：
  full   整屏（虚拟桌面，多屏也覆盖）
  region 鼠标框选一块（Ctrl+Shift+S）
  window 鼠标所在窗口
  long   连按两次，两段自动拼长图（60s 内没按第二次就取消）

截图不走键盘，避免被笔试平台记录键序；取消/排队由 Screenshotter 统一管。
"""
from __future__ import annotations

import io
import os
import queue
import threading
import time

LONG_TIMEOUT = float(os.getenv("SHOT_LONG_TIMEOUT", "60"))


def _grab_rect(bbox=None) -> bytes:
    from PIL import ImageGrab

    im = ImageGrab.grab(bbox=bbox, all_screens=True)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def grab_full() -> bytes:
    return _grab_rect()


def prepare(png: bytes, max_side: int = 1600, max_bytes: int = 900 * 1024) -> bytes:
    """送视觉模型前规整：
    - 长边 > max_side 缩小；长边 < 900 放大（题目区域常比整屏小，放大才能看清代码）；
    - 统一转 JPEG q=90，base64 payload 小 3-4 倍，TTFT 更快；
    - 结果比原图大就保留原图（扁平图 PNG 反而小）。
    """
    from PIL import Image

    im = Image.open(io.BytesIO(png)).convert("RGB")
    w, h = im.size
    m = max(w, h)
    if m > max_side:
        s = max_side / m
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    elif m < 900:
        s = min(2.0, 1100 / m)
        im = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    out = buf.getvalue()
    if len(out) >= len(png):  # 扁平图 PNG 更小，保留原图
        return png
    if len(out) > max_bytes:  # 超大图再降质量，避免 base64 撑大 TTFT
        q = 78
        while q > 40 and len(out) > max_bytes:
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=q)
            out = buf.getvalue()
            q -= 6
    return out


def grab_region(rect) -> bytes:
    """rect = (left, top, right, bottom)，全局坐标；太小就退整屏。"""
    if not rect:
        return grab_full()
    l, t, r, b = rect
    if r - l < 24 or b - t < 16:
        return grab_full()
    return _grab_rect((l, t, r, b))


def grab_window_at(x: int, y: int) -> bytes:
    """截鼠标所在窗口；拿不到窗口就退整屏。"""
    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32
    u.WindowFromPoint.restype = wintypes.HWND
    u.WindowFromPoint.argtypes = [wintypes.POINT]
    hwnd = u.WindowFromPoint(wintypes.POINT(x, y))
    if not hwnd:
        return grab_full()
    # 从命中点往上找顶层窗口，子控件截出来只有一小块
    root = u.GetAncestor(hwnd, 2)  # GA_ROOT
    if root:
        hwnd = root
    r = wintypes.RECT()
    if not u.GetWindowRect(hwnd, ctypes.byref(r)):
        return grab_full()
    w, h = r.right - r.left, r.bottom - r.top
    if w < 200 or h < 120:
        return grab_full()
    if u.IsIconic(hwnd):
        u.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.25)
        u.GetWindowRect(hwnd, ctypes.byref(r))
    return _grab_rect((r.left, r.top, r.right, r.bottom))


def stitch(a: bytes, b: bytes) -> bytes:
    """竖向拼接两张图，自动去掉重叠部分（长截图）。"""
    from PIL import Image

    ia = Image.open(io.BytesIO(a)).convert("RGB")
    ib = Image.open(io.BytesIO(b)).convert("RGB")
    if ia.width != ib.width:
        ib = ib.resize((ia.width, int(ib.height * ia.width / ib.width)))
    import numpy as np

    na, nb = np.asarray(ia), np.asarray(ib)
    h = min(na.shape[0], nb.shape[0])
    band = na[-min(60, h):].astype(np.int16)
    best, best_off = 1e9, 0
    for off in range(0, min(400, nb.shape[0] - band.shape[0])):
        cand = nb[off:off + band.shape[0]].astype(np.int16)
        err = float(np.abs(cand - band).mean())
        if err < best:
            best, best_off = err, off
    if best > 12:  # 没有明显重叠，直接接
        best_off = 0
    out = Image.new("RGB", (ia.width, na.shape[0] + nb.shape[0] - best_off))
    out.paste(ia, (0, 0))
    out.paste(ib, (0, na.shape[0] - best_off))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


class Screenshotter:
    """串行处理截图任务；同屏连续截图会排队，上一题做完自动跑下一张。"""

    def __init__(self, on_shot, ui_text, log=print,
                 before_grab=None, after_grab=None) -> None:
        # on_shot(png_bytes, cancel_evt) 由主程序提供（内部调 Brain.answer_image）
        self.on_shot = on_shot
        self.ui_text = ui_text
        self.log = log
        # 取图前/后回调：主程序用来把浮窗临时藏起来，避免截到自己
        self.before_grab = before_grab
        self.after_grab = after_grab
        self.q: "queue.Queue[tuple[str, bytes]]" = queue.Queue()
        self.cancel_evt = threading.Event()
        self.long_armed = False
        self.long_first = b""
        self.long_deadline = 0.0
        self.busy = False
        threading.Thread(target=self._loop, daemon=True).start()

    # ---- 取图
    def _grab(self, kind: str, x=None, y=None, rect=None) -> bytes:
        if self.before_grab:
            try:
                self.before_grab()
            except Exception:
                pass
        try:
            if kind == "region":
                return grab_region(rect)
            if kind == "window" and x is not None:
                return grab_window_at(x, y)
            return grab_full()
        finally:
            if self.after_grab:
                try:
                    self.after_grab()
                except Exception:
                    pass

    # ---- 触发
    def trigger(self, kind: str = "full", x: int | None = None, y: int | None = None,
                rect=None) -> None:
        kind = (kind or "full").lower()
        if kind == "long":
            self._long(x, y)
            return
        try:
            png = self._grab(kind, x, y, rect)
        except Exception as e:
            self.log(f"[shot] 取图失败 {type(e).__name__}: {e}")
            return
        self._enqueue(kind, png)

    def _long(self, x, y) -> None:
        try:
            png = self._grab("window" if x is not None else "full", x, y)
        except Exception as e:
            self.log(f"[shot] 长截图取图失败 {type(e).__name__}: {e}")
            return
        now = time.time()
        if self.long_armed and now <= self.long_deadline:
            first = self.long_first
            self.long_armed = False
            self.long_first = b""
            try:
                self._enqueue("long", stitch(first, png))
            except Exception as e:
                # 兜底：拼不上就把两段都送识别，宁可多一张也不丢内容
                self.log(f"[shot] 拼接失败 {type(e).__name__}: {e}，两段分别识别")
                self._enqueue("long", first)
                time.sleep(1.0)
                self._enqueue("long", png)
            return
        if self.long_armed:
            # 上一段已超时：先把上半段当单张识别，再以当前图作为新的上半段
            self.log("[shot] 长截图超时，上半段先单独识别")
            self._enqueue("long", self.long_first)
            self.long_first = b""
        self.long_armed = True
        self.long_first = png
        self.long_deadline = now + LONG_TIMEOUT
        self.ui_text(f"长截图：已记下上半段，{LONG_TIMEOUT:.0f} 秒内再触发一次")

    def _enqueue(self, kind: str, png: bytes) -> None:
        n = self.q.qsize() + (1 if self.busy else 0)
        if n:
            self.log(f"[shot] 已排队第 {n + 1} 张")
            self.ui_text(f"已排队第 {n + 1} 张 · 上一题完成后自动分析")
        self.q.put((kind, png))

    # ---- 取消
    def cancel(self) -> None:
        self.cancel_evt.set()
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
        self.long_armed = False
        self.long_first = b""
        self.log("[shot] 已取消当前截图/作答")

    # ---- 执行
    def _loop(self) -> None:
        while True:
            kind, png = self.q.get()
            self.busy = True
            self.cancel_evt.clear()
            t0 = time.time()
            self.log(f"[shot] {kind} 截图 {len(png) // 1024}KB → 识别中")
            try:
                self.on_shot(png, self.cancel_evt)
                self.log(f"[shot] {kind} 完成 {time.time() - t0:.2f}s")
            except Exception as e:
                self.log(f"[shot] 失败 {type(e).__name__}: {e}")
                self.ui_text(f"[截图识别失败] {type(e).__name__}: {e}")
            finally:
                self.busy = False
            if not self.q.empty():
                time.sleep(1.0)  # 连拍排队时两张之间隔 1 秒，避免把同一页截两遍
