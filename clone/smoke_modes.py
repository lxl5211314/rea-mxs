# -*- coding: utf-8 -*-
"""双模式冒烟：interview 12s / exam 12s，记录 alive、stderr 字节、关键日志。"""
import os
import subprocess
import sys
import time

OUT = open("smoke_modes.log", "w", encoding="utf-8")


def run(mode, secs):
    env = dict(os.environ, MODE=mode, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.pop("EXAM_GHOST", None)  # 用 .env 里的默认值
    p = subprocess.Popen([sys.executable, "mvp.py"], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    time.sleep(secs)
    alive = p.poll() is None
    p.terminate()
    try:
        out, err = p.communicate(timeout=8)
    except Exception:
        p.kill()
        out, err = "", ""
    lines = [l for l in out.splitlines() if any(k in l for k in
                                               ("[ghost]", "[mode]", "[capture]", "[asr]", "[dom]", "[stealth]", "[hotkey]"))]
    s = f"== {mode} alive={alive} stderr={len(err)}"
    print(s, flush=True)
    OUT.write(s + "\n")
    for l in lines[:8]:
        print("  " + l[:120], flush=True)
        OUT.write("  " + l[:120] + "\n")
    if err.strip():
        OUT.write("ERR: " + err[:400] + "\n")
    OUT.flush()


run("interview", 14)
run("exam", 12)
OUT.close()
