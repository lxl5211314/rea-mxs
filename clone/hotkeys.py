"""全局热键 + 鼠标截图手势。

键盘用 keyboard 库；鼠标手势走 WH_MOUSE_LL 低级钩子，不产生按键事件，
所以笔试平台的键盘监控看不到任何记录。

默认手势（和面试侠一致）：
    Shift + 双击      整屏截图
    Alt + 双击        窗口截图（鼠标所在窗口）
    Shift + Alt + 双击 长截图（60 秒内连做两次）
"""
from __future__ import annotations

import ctypes
import queue
import threading
import time
from ctypes import wintypes

VK_SHIFT = 0x10
VK_MENU = 0x12
VK_CONTROL = 0x11
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MBUTTONDOWN = 0x0207
WM_XBUTTONDOWN = 0x020B
WH_MOUSE_LL = 14


def _mods_now(user32) -> tuple[str, ...]:
    out = []
    if user32.GetAsyncKeyState(VK_SHIFT) & 0x8000:
        out.append("shift")
    if user32.GetAsyncKeyState(VK_MENU) & 0x8000:
        out.append("alt")
    if user32.GetAsyncKeyState(VK_CONTROL) & 0x8000:
        out.append("ctrl")
    return tuple(out)


class MouseHooks:
    """鼠标截图手势。clicks/button/mods 可配（对应官网「修饰键和点击方式可改」）。"""

    def __init__(self, on_shot, log=print, clicks: int = 2, button: str = "left",
                 mods: dict | None = None, interval: float = 0.85, dist: int = 24) -> None:
        self.on_shot = on_shot
        self.log = log
        self.clicks = max(1, min(3, int(clicks)))
        self.button = (button or "left").lower()
        self.mods = mods or {"full": ("shift",), "window": ("alt",), "long": ("shift", "alt")}
        # 双击间隔按 Windows 默认双击速度（500ms）留余量；手慢一点也能触发
        self.interval = float(interval)
        self.dist = int(dist)
        self._hook = None
        self._last_t = 0.0
        self._last_pt = (0, 0)
        self._streak = 0
        self._proc = None
        self._q = None

    def _kind_for(self, mods: tuple[str, ...]) -> str | None:
        have = set(mods)
        for kind in ("long", "window", "full"):
            want = set(self.mods.get(kind, ()))
            if want and want <= have and not (have - want):
                return kind
        return None

    def _matches_button(self, wparam) -> bool:
        return {
            "left": WM_LBUTTONDOWN,
            "right": WM_RBUTTONDOWN,
            "middle": WM_MBUTTONDOWN,
            "x": WM_XBUTTONDOWN,
        }.get(self.button, WM_LBUTTONDOWN) == wparam

    def start(self) -> None:
        user32 = ctypes.windll.user32

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        # 不声明 argtypes 时第 4 个参数按 c_int 转换，64 位指针会 OverflowError
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          wintypes.WPARAM, wintypes.LPARAM]

        def proc(nCode, wParam, lParam):
            try:
                if nCode >= 0 and self._matches_button(wParam):
                    info = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    x, y = info.pt.x, info.pt.y
                    now = time.time()
                    mods = _mods_now(user32)
                    near = abs(x - self._last_pt[0]) < self.dist and abs(y - self._last_pt[1]) < self.dist
                    if near and now - self._last_t < self.interval:
                        self._streak += 1
                    else:
                        self._streak = 1
                    self._last_t, self._last_pt = now, (x, y)
                    kind = self._kind_for(mods)
                    if kind and self._streak >= self.clicks:
                        self._streak = 0
                        self._last_t = 0.0
                        # 钩子回调里只入队：在这里开线程/调 Qt 都可能触发 0xC000041D
                        self._q.put((kind, x, y))
                        return 1  # 吞掉这次点击，别让被截的程序收到
            except Exception:
                pass
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._q = queue.Queue()

        def worker() -> None:
            while True:
                kind, x, y = self._q.get()
                try:
                    self.on_shot(kind, x, y)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

        self._proc = HOOKPROC(proc)
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        if not self._hook:
            self.log("[hotkey] 鼠标钩子安装失败（截图手势不可用，仍可用热键）")
            return

        def loop():
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        threading.Thread(target=loop, daemon=True).start()
        names = {"shift": "Shift", "alt": "Alt", "ctrl": "Ctrl"}
        btn = {"left": "左键", "right": "右键", "middle": "中键", "x": "侧键"}.get(self.button, "左键")
        click = {1: "单击", 2: "双击", 3: "三连击"}.get(self.clicks, f"{self.clicks}连击")
        parts = []
        for kind, label in (("full", "整屏"), ("window", "窗口"), ("long", "长截图")):
            m = "+".join(names.get(k, k) for k in self.mods.get(kind, ()))
            if m:
                parts.append(f"{m}+{click}{btn}{label}")
        self.log("[hotkey] 鼠标手势：" + " / ".join(parts))


def install(cb: dict, log=print, post=None) -> list[str]:
    """cb 的键：toggle, exit, prev, next, pin, force, cancel, region, opacity_up, opacity_down,
    scale_up, scale_down, scroll_up, scroll_down, copy, help, clear, click_through, theme。
    返回已装上的组合键。

    默认 suppress=True：这些组合键不会漏给前台程序（浏览器/笔试页面看不到按键，也不会
    触发 Ctrl+Shift+B 书签栏、Ctrl+Shift+S 另存为这类副作用）。HOTKEY_SUPPRESS=0 可关。
    """
    import os

    import keyboard  # type: ignore

    suppress = os.getenv("HOTKEY_SUPPRESS", "1") not in ("0", "false", "False")

    done: list[str] = []
    last_q = [0.0]

    def _exit():
        now = time.time()
        if now - last_q[0] < 3.0:
            cb["exit"]()
        else:
            last_q[0] = now
            log("[hotkey] 再按一次 Ctrl+Shift+Q 结束本场（3 秒内）")

    table = [
        ("ctrl+shift+b", "toggle", cb.get("toggle")),
        ("ctrl+shift+q", "exit", _exit),
        ("ctrl+shift+up", "prev", cb.get("prev")),
        ("ctrl+shift+down", "next", cb.get("next")),
        ("ctrl+shift+p", "pin", cb.get("pin")),
        ("ctrl+shift+g", "force", cb.get("force")),
        ("ctrl+shift+r", "retake", cb.get("retake")),
        ("ctrl+shift+x", "cancel", cb.get("cancel")),
        ("ctrl+shift+s", "region", cb.get("region")),
        # 键盘版截图（双击手势对手速敏感时用这个，一定生效）
        # 注意：按住 Shift 时数字键产生的是 !/@/#，keyboard 按名字匹配，
        # 必须注册移位后的符号；注册 "1"/"2"/"3" 永远匹配不上，而且会误触方向键。
        ("ctrl+shift+!", "shot_full", cb.get("shot_full")),
        ("ctrl+shift+@", "shot_window", cb.get("shot_window")),
        ("ctrl+shift+#", "shot_long", cb.get("shot_long")),
        ("ctrl+shift+l", "list", cb.get("list")),
        ("ctrl+shift+d", "dom", cb.get("dom")),
        ("ctrl+shift+u", "follow", cb.get("follow")),
        ("ctrl+alt+=", "opacity_up", cb.get("opacity_up")),
        ("ctrl+alt+-", "opacity_down", cb.get("opacity_down")),
        # Shift+=/- 实际产生的是 "+"/"_"，按名字匹配不上，改用不受 Shift 影响的方向键
        ("ctrl+alt+up", "scale_up", cb.get("scale_up")),
        ("ctrl+alt+down", "scale_down", cb.get("scale_down")),
        # Alt+Shift 是 Windows 切换输入法的系统组合，Alt+Shift+↑/↓ 收不到，滚动改用鼠标滚轮
        ("ctrl+shift+c", "copy", cb.get("copy")),
        ("ctrl+shift+h", "help", cb.get("help")),
        ("ctrl+shift+backspace", "clear", cb.get("clear")),
        ("f8", "toggle", cb.get("toggle")),
        ("f9", "click_through", cb.get("click_through")),
        ("f10", "opacity", cb.get("opacity_down")),
        ("shift+up", "move_up", cb.get("move_up")),
        ("shift+down", "move_down", cb.get("move_down")),
        ("shift+left", "move_left", cb.get("move_left")),
        ("shift+right", "move_right", cb.get("move_right")),
        ("ctrl+alt+y", "theme", cb.get("theme")),
        ("ctrl+alt+g", "grid", cb.get("grid")),
        ("ctrl+alt+m", "compact", cb.get("compact")),
        ("ctrl+alt+s", "toggle", cb.get("toggle")),
    ]
    # 方向键要留给输入框/代码编辑器选文字，不能全局吞掉
    loose = {"shift+up", "shift+down", "shift+left", "shift+right"}
    for combo, name, fn in table:
        if not fn:
            continue
        try:
            def _wrap(fn=fn, name=name):
                def inner():
                    if os.getenv("HOTKEY_DEBUG"):
                        log(f"[hotkey] 触发 {name}")
                    # post: 钩子线程里不能碰 Qt，交给主线程执行（0xC000041D 的根因）
                    if post is not None:
                        try:
                            post(name, fn)
                        except Exception as e:
                            log(f"[hotkey] {name} 派发失败 {type(e).__name__}: {e}")
                        return None
                    try:
                        return fn()
                    except Exception as e:
                        log(f"[hotkey] {name} 出错 {type(e).__name__}: {e}")
                return inner

            keyboard.add_hotkey(combo, _wrap(), suppress=suppress and combo not in loose)
            done.append(combo)
        except Exception as e:
            log(f"[hotkey] {combo} 注册失败 {type(e).__name__}: {e}")
    log("[hotkey] 已启用：" + " / ".join(done))
    return done


HELP_TEXT = """快捷键
Ctrl+Shift+B  显示/隐藏（隐藏后按 F8 或 Ctrl+Alt+S 叫回来）
F8 / Ctrl+Alt+S  显示/隐藏（等价）
Ctrl+Shift+Q  结束本场（3 秒内按两次）
Ctrl+Shift+↑/↓ 上一题/下一题
Ctrl+Shift+P  钉住当前答案
Ctrl+Shift+G  笔试=重新识别当前截图 / 面试=强制提交当前文字
Ctrl+Shift+R  重新截一张（笔试）/ 重答上一题（面试）
Ctrl+Shift+X  取消当前截图/作答
Ctrl+Shift+S  框选一块区域截图
Ctrl+Shift+1  整屏截图（键盘版，比双击稳）
Ctrl+Shift+2  截鼠标所在窗口
Ctrl+Shift+3  长截图（同一位置再按一次拼下半屏）
Ctrl+Shift+L  题目列表（再按返回）
Ctrl+Shift+D  从页面读题（DOM，优先 CDP）
Ctrl+Shift+U  追问预判（列出可能的追问）
Shift+方向键  移动窗口（20px）
Ctrl+Alt+=/-  变亮/变淡
Ctrl+Alt+↑/↓  放大/缩小
滚轮：答案上下滚动（浮窗任意位置）
Ctrl+Shift+C  复制当前答案
Ctrl+Alt+Y    切换样式（极暗/蓝灰/大字）
Ctrl+Alt+G    图形准备页（网格+涂鸦，右键清空）
Ctrl+Alt+M    迷你窗 / 标准窗（也可点右下角「小」）
Shift+双击    整屏截图
Alt+双击      窗口截图
Shift+Alt+双击 长截图
Ctrl+Shift+Backspace 清空当前答案
Ctrl+Shift+H 显示这份快捷键
F8 显示/隐藏   F9 点击穿透   F10 变淡"""
