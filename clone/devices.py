r"""音频设备与回环采集诊断（不依赖 pycaw，避免 COM 崩溃）。

用法：
  python devices.py                     # 只列设备
  python devices.py -w 文件.wav         # 播 wav 并抓默认输出设备的回环
  python devices.py -w 文件.wav -d "耳机"  # 指定设备名（子串匹配）
"""
from __future__ import annotations

import argparse
import os
import queue
import threading
import time
import wave

import numpy as np
import soundcard as sc

SR, B = 16000, 1600


def coinit() -> None:
    import ctypes

    ctypes.windll.ole32.CoInitializeEx(None, 0x2)


def list_devices() -> None:
    print("== speakers ==")
    for s in sc.all_speakers():
        print(f"  {s.name!r}  ch={s.channels}")
    print("== loopback-capable devices ==")
    for m in sc.all_microphones(include_loopback=True):
        print(f"  {m.name!r}  loopback={getattr(m, 'isloopback', None)}")
    print("default speaker:", sc.default_speaker().name)


def pick(name_hint: str | None):
    """返回 (显示名, speaker.id)。按 id 解析回环设备，避免命中同名麦克风端点。"""
    if not name_hint:
        spk = sc.default_speaker()
        return spk.name, str(spk.id)
    for s in sc.all_speakers():
        if name_hint.lower() in s.name.lower():
            return s.name, str(s.id)
    raise SystemExit(f"没找到名字含 {name_hint!r} 的输出设备")


def capture(dev: str, secs: float) -> np.ndarray:
    q: queue.Queue = queue.Queue()

    def run() -> None:
        coinit()
        mic = sc.get_microphone(id=dev, include_loopback=True)
        try:
            with mic.recorder(samplerate=SR, channels=1, blocksize=B) as r:
                t0 = time.time()
                while time.time() - t0 < secs:
                    q.put(r.record(numframes=B)[:, 0])
        except Exception as e:
            print(f"[cap] {type(e).__name__}: {e}")

    th = threading.Thread(target=run)
    th.start()
    th.join()
    blocks = list(q.queue)
    return np.concatenate(blocks) if blocks else np.zeros(1, dtype=np.float32)


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        n = int(round(len(x) * SR / sr))
        x = np.interp(np.linspace(0, 1, n, endpoint=False),
                      np.linspace(0, 1, len(x), endpoint=False), x).astype(np.float32)
    return x


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-w", "--wav")
    ap.add_argument("-d", "--device")
    ap.add_argument("-s", "--seconds", type=float, default=8.0)
    a = ap.parse_args()

    list_devices()
    if not a.wav:
        return 0
    dev_name, dev_id = pick(a.device)
    print(f"采集设备: {dev_name!r}  loopback_id={dev_id}")

    q: queue.Queue = queue.Queue()

    def run() -> None:
        coinit()
        mic = sc.get_microphone(id=dev_id, include_loopback=True)
        with mic.recorder(samplerate=SR, channels=1, blocksize=B) as r:
            t0 = time.time()
            while time.time() - t0 < a.seconds:
                q.put(r.record(numframes=B)[:, 0])

    th = threading.Thread(target=run)
    th.start()
    time.sleep(0.5)
    src = read_wav(a.wav)
    print(f"播放 {os.path.basename(a.wav)}（{len(src)/SR:.2f}s, rms={float(np.sqrt(np.mean(src**2))):.4f}）")

    import winsound

    winsound.PlaySound(a.wav, winsound.SND_FILENAME)
    time.sleep(0.4)
    th.join()

    blocks = list(q.queue)
    a2 = np.concatenate(blocks) if blocks else np.zeros(1, dtype=np.float32)
    print(f"抓回 {len(a2)/SR:.2f}s rms={float(np.sqrt(np.mean(a2**2))):.4f} peak={float(np.max(np.abs(a2))):.3f}")
    prof = [round(float(np.sqrt(np.mean(a2[i:i + 8000] ** 2))), 4) for i in range(0, max(1, len(a2) - 8000), 8000)]
    print("每 0.5s RMS:", prof[:20])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
