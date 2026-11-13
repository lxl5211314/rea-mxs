# -*- coding: utf-8 -*-
"""控制台窗口开关：show / hide / min。

mvp.py 启动时会把控制台藏起来（整屏共享看不到）。程序异常退出时，
start-exam.bat 调这里把控制台重新显示出来，好让人看到报错和 run.log。
"""
import ctypes
import sys


def hwnd():
    k32 = ctypes.windll.kernel32
    k32.GetConsoleWindow.restype = ctypes.c_void_p
    return k32.GetConsoleWindow()


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "show").lower()
    h = hwnd()
    if not h:
        return 1
    u = ctypes.windll.user32
    code = {"show": 5, "hide": 0, "min": 6}.get(mode, 5)
    u.ShowWindow(h, code)
    u.SetForegroundWindow(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
