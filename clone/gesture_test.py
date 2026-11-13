"""动作捕捉离线自检：不接 mvp，直接跑摄像头 N 秒，打印进度/触发。

用法：python gesture_test.py [glasses|blink] [秒数]
"""
import os
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "glasses"
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0

from gesture import GestureWatcher

lines = []


def log(msg):
    lines.append(msg)
    print(msg, flush=True)


def prog(p, t):
    if t:
        log(f"[prog] {p:.2f} {t}")


g = GestureWatcher(lambda kind: log(f"[TRIGGER] {kind}"), on_progress=prog, log=log, mode=mode)
g.start()
time.sleep(dur)
g.stop()
time.sleep(1.0)
log(f"[done] 触发 {g.count} 次，错误 {g.error}")
open(r"E:\aaa_msx\clone\gesture_test.log", "w", encoding="utf-8").write("\n".join(lines))
