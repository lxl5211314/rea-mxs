# -*- coding: utf-8 -*-
"""看护进程：拉起 mvp.py 并盯住它；异常退出自动重启，正常退出（0）就结束。

用法（在 clone 目录）：
    python guardian.py              # 看护 mvp.py
    python guardian.py --no-ui      # 参数透传给 mvp.py
    python guardian.py 别的脚本.py   # 看护指定脚本

环境：
    GUARDIAN_MAX=0     最多重启次数（0=不限）
    GUARDIAN_DELAY=1.5 首次重启等待秒数；之后按 1.5/3/5 退避

日志：guardian.log（utf-8），子进程输出同时转发到控制台。
"""
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "guardian.log")
MAX = int(os.getenv("GUARDIAN_MAX", "0") or 0)
DELAY = float(os.getenv("GUARDIAN_DELAY", "1.5") or 1.5)

_log_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[guard] {msg}"
    with _log_lock:
        print(line, flush=True)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        except Exception:
            pass
        try:
            # 同一份 run.log 里留一行，崩溃后一眼能看出「是自愈拉起来的」
            with open(os.path.join(HERE, "run.log"), "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%m-%d %H:%M:%S')} [guard:{os.getpid()}] {msg}\n")
        except Exception:
            pass


def _args() -> list[str]:
    argv = sys.argv[1:]
    if argv and argv[0].lower().endswith(".py"):
        return [sys.executable, argv[0], *argv[1:]]
    return [sys.executable, os.path.join(HERE, "mvp.py"), *argv]


def _pump(proc: subprocess.Popen, stop: threading.Event) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        if stop.is_set():
            break
        print(line.rstrip("\n"), flush=True)
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass


def main() -> int:
    cmd = _args()
    restarts = 0
    while True:
        log("启动 " + " ".join(cmd))
        t0 = time.time()
        try:
            proc = subprocess.Popen(
                cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
        except Exception as e:
            log(f"启动失败 {type(e).__name__}: {e}")
            return 2
        stop = threading.Event()
        th = threading.Thread(target=_pump, args=(proc, stop), daemon=True)
        th.start()
        try:
            code = proc.wait()
        except KeyboardInterrupt:
            log("收到 Ctrl+C，结束子进程")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
            stop.set()
            return 0
        stop.set()
        th.join(timeout=2)
        alive = time.time() - t0
        if code == 0:
            log("子进程正常退出，看护结束")
            return 0
        if MAX and restarts >= MAX:
            log(f"已重启 {restarts} 次，达到 GUARDIAN_MAX，放弃（退出码 {code}）")
            return code or 1
        restarts += 1
        wait = min(5.0, DELAY * (1.5 ** (restarts - 1)))
        log(f"子进程退出码 {code}（运行 {alive:.1f}s），{wait:.1f}s 后第 {restarts} 次重启")
        time.sleep(wait)


if __name__ == "__main__":
    sys.exit(main())
