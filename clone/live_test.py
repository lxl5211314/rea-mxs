"""实机冒烟：后台起 mvp.py --no-ui，前台播放一段面试官提问，看它是否自动听到并作答。

   python live_test.py                       # 用内置 self-test wav
   python live_test.py path\to.wav 25        # 自定义 wav + 播完后等几秒

输出同时写 live.log（utf-8），避免 PowerShell 控制台 GBK 把中文打成乱码。
"""
import os
import subprocess
import sys
import time

WAV = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\msx-client\resources\self-test-interviewer.wav"
WAIT = float(sys.argv[2]) if len(sys.argv) > 2 else 25.0
CLONE = r"E:\aaa_msx\clone"
OUT = os.path.join(CLONE, "live.log")

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env.setdefault("ASR_MODEL", "faster-whisper-base")

p = subprocess.Popen([sys.executable, "mvp.py", "--no-ui"], cwd=CLONE, env=env,
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                     encoding="utf-8", errors="replace", bufsize=1)

lines: list[str] = []


def pump() -> None:
    assert p.stdout is not None
    for line in p.stdout:
        lines.append(line)
        print(line, end="", flush=True)


import threading

t = threading.Thread(target=pump, daemon=True)
t.start()

time.sleep(9)  # 等模型加载完
print(">>> 播放测试音频", flush=True)
subprocess.run(["python", "-c",
                f"import winsound;winsound.PlaySound(r'{WAV}', winsound.SND_FILENAME)"], check=False)
time.sleep(WAIT)
p.terminate()
try:
    p.wait(timeout=5)
except subprocess.TimeoutExpired:
    p.kill()
t.join(timeout=3)

with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"# wav={WAV}\n# wait={WAIT}s\n" + "".join(lines))
print(f"----- 已写入 {OUT} -----")
