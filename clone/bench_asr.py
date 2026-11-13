r"""ASR 延迟基准：冷启动 vs 热跑，不同模型大小。

  python bench_asr.py -w 文件.wav            # 默认 small
  python bench_asr.py -w 文件.wav -m base
"""
from __future__ import annotations

import argparse
import time
import wave

import numpy as np

SR = 16000


def read(p):
    with wave.open(p, "rb") as w:
        ch, sr = w.getnchannels(), w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    if sr != SR:
        n = int(len(x) * SR / sr)
        x = np.interp(np.linspace(0, 1, n, endpoint=False), np.linspace(0, 1, len(x), endpoint=False), x)
    return x.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--wav", required=True)
    ap.add_argument("-m", "--model", default="small")
    ap.add_argument("-d", "--device", default="cpu", choices=["cpu", "cuda"])
    a = ap.parse_args()

    pcm = read(a.wav)
    print(f"音频 {len(pcm)/SR:.2f}s  rms={float(np.sqrt(np.mean(pcm**2))):.3f}")

    import mvp

    _add = getattr(mvp, "_add_cuda_dlls", None)
    if _add:
        _add()

    from faster_whisper import WhisperModel

    t0 = time.time()
    m = WhisperModel(a.model, device=a.device,
                     compute_type="float16" if a.device == "cuda" else "int8")
    print(f"加载模型 {time.time()-t0:.2f}s  device={a.device}")

    for i in range(3):
        t0 = time.time()
        segs, info = m.transcribe(pcm, language="zh", beam_size=1, vad_filter=False,
                                  initial_prompt="以下是普通话面试对话，请用简体中文输出。")
        text = "".join(s.text for s in segs).strip()
        print(f"第 {i+1} 次: {time.time()-t0:.2f}s  (语音{speech_dur(info, segs):.1f}s)  → {text}")


def speech_dur(info, segs):
    return float(getattr(info, "duration", 0) or 0)


if __name__ == "__main__":
    main()
