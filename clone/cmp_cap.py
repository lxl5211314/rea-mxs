import wave

import numpy as np

SR = 16000


def read(p):
    with wave.open(p, "rb") as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    if sr != SR:
        n = int(len(x) * SR / sr)
        x = np.interp(np.linspace(0, 1, n, endpoint=False), np.linspace(0, 1, len(x), endpoint=False), x)
    return x


src = read(r"C:\Program Files\msx-client\resources\self-test-interviewer.wav")
cap = read(r"E:\aaa_msx\clone\e2e_capture.wav")
print("src", len(src), "cap", len(cap), "src rms", round(float(np.sqrt(np.mean(src**2))), 4),
      "cap rms", round(float(np.sqrt(np.mean(cap**2))), 4))

n = len(src) + len(cap)
X = np.fft.rfft(src, n)
Y = np.fft.rfft(cap, n)
cc = np.fft.irfft(X * np.conj(Y), n)
lag = int(np.argmax(np.abs(cc[: len(cap)])))
peak = float(cc[lag] / (np.linalg.norm(src[: len(cap)] if len(src) > len(cap) else src) * np.linalg.norm(cap) + 1e-9))
print("best lag(s):", round(lag / SR, 3), "normalized corr:", round(peak, 3))

# 频带能量对比
def band(x):
    f = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1 / SR)
    out = {}
    for lo, hi in ((0, 300), (300, 1000), (1000, 3000), (3000, 8000)):
        m = (freqs >= lo) & (freqs < hi)
        out[f"{lo}-{hi}"] = round(float(f[m].mean()), 1)
    return out


print("src bands", band(src))
print("cap bands", band(cap))
