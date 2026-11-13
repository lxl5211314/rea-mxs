"""无界面冒烟：把 e2e_capture.wav 灌进 VAD → ASR → 问题判定 → LLM（无 key 时应优雅报错）。"""
import sys
import time
import wave

import numpy as np

sys.path.insert(0, r"E:\aaa_msx\clone")
import mvp  # noqa: E402

p = sys.argv[1] if len(sys.argv) > 1 else r"E:\aaa_msx\clone\e2e_capture.wav"
with wave.open(p, "rb") as w:
    pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768

print(f"输入 {len(pcm)/mvp.SR:.2f}s rms={float(np.sqrt(np.mean(pcm**2))):.3f}")
print("asr model:", mvp.ASR_MODEL)

# 分块喂 VAD
import queue

rq, sq = queue.Queue(), queue.Queue()
vad = mvp.VadSegmenter(rq, sq)
vad.start()
for i in range(0, len(pcm), mvp.BLOCK):
    rq.put(pcm[i:i + mvp.BLOCK])
time.sleep(1.0)

seg = sq.get(timeout=10)
print(f"VAD 段 {len(seg)/mvp.SR:.2f}s")
asr = mvp.Asr()
t0 = time.time()
text = asr.transcribe(seg)
print(f"ASR {time.time()-t0:.2f}s -> {text}")
print("是问题:", mvp.is_question(text))

b = mvp.Brain("后端工程师", "订单中心重构，QPS 800->6000")
try:
    out = b.answer(text, lambda s: None)
    print("LLM:", out)
except Exception as e:
    print(f"LLM 不可用（预期，缺 key）：{type(e).__name__}: {e}")
