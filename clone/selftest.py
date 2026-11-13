r"""自检脚本：逐层验证 msx-clone 的每个环节。

用法：
  python selftest.py deps                 # 依赖/设备清单
  python selftest.py capture -s 5         # 录 5 秒 loopback，报 RMS
  python selftest.py asr -w 文件.wav      # 对一个 wav 跑 ASR
  python selftest.py e2e -w 文件.wav      # 播放 wav 同时抓 loopback -> VAD -> ASR（全链路）
  python selftest.py llm -q "做个自我介绍"  # 测 LLM（需要 OPENAI_API_KEY）

全链路 e2e 不需要麦克风、不需要开会：把面试侠自带的
  C:\Program Files\msx-client\resources\self-test-interviewer.wav
当作"面试官"播出来，脚本从系统回环里把它抓回来。
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
import wave

import numpy as np

SR = 16000
BLOCK = 1600


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst:
        return x
    n = int(round(len(x) * dst / src))
    if n <= 1:
        return x.astype(np.float32)
    xp = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
    xq = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(xq, xp, x).astype(np.float32)


# ---------------------------------------------------------------- deps
def cmd_deps(_args) -> int:
    info: dict = {"python": sys.version.split()[0]}
    for m in ("soundcard", "numpy", "PySide6", "keyboard", "openai",
              "faster_whisper", "ctranslate2"):
        try:
            mod = __import__(m)
            info[m] = getattr(mod, "__version__", "ok")
        except Exception as e:
            info[m] = f"MISSING ({type(e).__name__})"
    try:
        import soundcard as sc
        info["default_speaker"] = sc.default_speaker().name
        info["speakers"] = [s.name for s in sc.all_speakers()]
        info["loopback_devices"] = [m.name for m in sc.all_microphones(include_loopback=True)]
    except Exception as e:
        info["soundcard_error"] = f"{type(e).__name__}: {e}"
    try:
        import mvp  # 触发 .env 加载

        info["ASR_MODEL"] = mvp.ASR_MODEL
        info["ASR_EXISTS"] = os.path.isdir(mvp.ASR_MODEL) if os.path.sep in mvp.ASR_MODEL else "repo"
    except Exception:
        pass
    info["OPENAI_API_KEY"] = "set" if os.getenv("OPENAI_API_KEY") else "MISSING"
    info["OPENAI_BASE_URL"] = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    info["LLM_MODEL"] = os.getenv("LLM_MODEL", "deepseek-chat")
    info["LLM_REASONING_EFFORT"] = os.getenv("LLM_REASONING_EFFORT", "")
    info["EARLY_ASK"] = os.getenv("EARLY_ASK", "1")
    info["PARTIAL_STEP"] = os.getenv("PARTIAL_STEP", "1.2")
    if info["OPENAI_BASE_URL"].startswith("http://127.0.0.1"):
        import urllib.request

        try:
            urllib.request.urlopen(info["OPENAI_BASE_URL"].rstrip("/") + "/models", timeout=3)
            info["relay_reachable"] = True
        except Exception as e:
            info["relay_reachable"] = f"{type(e).__name__}: {e}"
    print(json.dumps(info, ensure_ascii=False, indent=1))
    return 0


# ---------------------------------------------------------------- capture
def _open_loopback(samplerate: int, blocksize: int):
    import soundcard as sc

    spk = sc.default_speaker()
    # 按 spk.id 解析，按 name 会命中同名麦克风端点
    mic = sc.get_microphone(id=str(spk.id), include_loopback=True)
    return mic.recorder(samplerate=samplerate, channels=1, blocksize=blocksize)


def record(seconds: float) -> np.ndarray:
    """优先 16k 直采，设备不支持则 48k 采集 + 线性重采样。"""
    total = int(seconds * SR)
    try:
        rec = _open_loopback(SR, BLOCK)
        with rec:
            chunks = [rec.record(numframes=BLOCK)[:, 0] for _ in range(max(1, total // BLOCK))]
        return np.concatenate(chunks).astype(np.float32)
    except Exception as e:
        print(f"[capture] 16k 失败({type(e).__name__}: {e})，改用 48k+重采样", flush=True)
        blocks = 4800
        rec = _open_loopback(48000, blocks)
        with rec:
            chunks = [rec.record(numframes=blocks)[:, 0] for _ in range(max(1, total // 1600))]
        return _resample(np.concatenate(chunks).astype(np.float32), 48000, SR)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2)) + 1e-9)


def cmd_capture(args) -> int:
    print(f"录 {args.seconds}s（现在让系统播放点声音）…", flush=True)
    pcm = record(args.seconds)
    print(f"采样点={len(pcm)}  时长={len(pcm)/SR:.2f}s  RMS={rms(pcm):.4f}  "
          f"峰值={float(np.max(np.abs(pcm))):.4f}")
    if rms(pcm) < 0.001:
        print("→ 近乎静音：系统没在播放声音，或默认输出设备不是正在出声的那个。")
    return 0


# ---------------------------------------------------------------- asr
def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        ch, sw, sr = w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise SystemExit(f"只支持 16bit wav，当前 {sw*8}bit")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return _resample(x, sr, SR)


_ASR = None


def get_asr():
    global _ASR
    if _ASR is None:
        from faster_whisper import WhisperModel

        import mvp

        name = mvp.resolve_asr_model(os.getenv("ASR_MODEL", "faster-whisper-base"))
        print(f"[asr] 加载 faster-whisper {name}", flush=True)
        _ASR = WhisperModel(name, device="cpu", compute_type="int8")
    return _ASR


def transcribe(pcm: np.ndarray) -> str:
    pcm = _normalize(pcm, 0.9) if float(np.max(np.abs(pcm)) if len(pcm) else 0) < 0.5 else pcm
    segs, _ = get_asr().transcribe(
        pcm, language="zh", beam_size=1, vad_filter=False,
        initial_prompt="以下是普通话面试对话，请用简体中文输出。",
    )
    return "".join(s.text for s in segs).strip()


def cmd_asr(args) -> int:
    pcm = read_wav(args.wav)
    t0 = time.time()
    text = transcribe(pcm)
    print(f"[{time.time()-t0:.2f}s] {text}")
    return 0


# ---------------------------------------------------------------- e2e
def _normalize(x: np.ndarray, target_peak: float = 0.9) -> np.ndarray:
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak < 1e-6:
        return x.astype(np.float32)
    return (x * (target_peak / peak)).astype(np.float32)


def write_wav(path: str, pcm: np.ndarray) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())


def cmd_e2e(args) -> int:
    """播放 wav（走系统默认输出）→ 同时抓 loopback → VAD 切句 → ASR。"""
    import tempfile
    import winsound

    pcm_file = read_wav(args.wav)
    dur = len(pcm_file) / SR
    out_q: "queue.Queue[np.ndarray]" = queue.Queue()

    stop = threading.Event()

    def cap() -> None:
        try:
            rec = _open_loopback(SR, BLOCK)
            with rec:
                while not stop.is_set():
                    out_q.put(rec.record(numframes=BLOCK)[:, 0].astype(np.float32))
        except Exception as e:
            print(f"[cap] 16k 失败({e})，改 48k", flush=True)
            rec = _open_loopback(48000, 4800)
            with rec:
                while not stop.is_set():
                    out_q.put(_resample(rec.record(numframes=4800)[:, 0].astype(np.float32), 48000, SR))

    t = threading.Thread(target=cap, daemon=True)
    t.start()
    time.sleep(0.4)
    # 播一份峰值归一化到 0.9 的副本，避免"设备音量太小 -> 抓回全静音"的假阴性
    play_path = os.path.join(tempfile.gettempdir(), "msx_e2e_play.wav")
    write_wav(play_path, _normalize(pcm_file))
    winsound.PlaySound(play_path, winsound.SND_FILENAME)
    time.sleep(0.3)
    stop.set()
    time.sleep(0.3)

    chunks = []
    while not out_q.empty():
        chunks.append(out_q.get())
    pcm = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    print(f"[e2e] 抓回 {len(pcm)/SR:.2f}s（源 {dur:.2f}s） RMS={rms(pcm):.4f}（源 RMS={rms(pcm_file):.4f}）")
    dump = "e2e_capture.wav"
    write_wav(dump, pcm)
    print(f"[e2e] 抓回的音频已存到 {os.path.abspath(dump)}")
    pcm = _normalize(pcm, 0.9)

    whole = transcribe(pcm)
    print(f"[e2e] 整段直接 ASR：{whole}")

    # 简单 VAD 切片
    segs, cur, speech, silence = [], [], 0.0, 0.0
    noise = 0.002
    for i in range(0, len(pcm) - BLOCK, BLOCK):
        blk = pcm[i:i + BLOCK]
        r = rms(blk)
        if r < noise * 1.5:
            noise = 0.98 * noise + 0.02 * r
        if r > max(0.006, noise * 2.5):
            cur.append(blk); speech += BLOCK / SR; silence = 0.0
        elif cur:
            cur.append(blk); silence += BLOCK / SR
            if silence >= 0.6:
                if speech >= 0.5:
                    segs.append(np.concatenate(cur))
                cur, speech, silence = [], 0.0, 0.0
    if cur and speech >= 0.5:
        segs.append(np.concatenate(cur))

    print(f"[e2e] VAD 切出 {len(segs)} 段：{[round(len(s)/SR,2) for s in segs]}")
    if not segs:
        print("→ 没抓到语音，检查默认输出设备/音量。")
        return 1
    for k, s in enumerate(segs, 1):
        t0 = time.time()
        text = transcribe(s)
        print(f"[{k}] ASR {time.time()-t0:.2f}s（{len(s)/SR:.1f}s 音频）→ {text}", flush=True)
    return 0


# ---------------------------------------------------------------- llm
def cmd_llm(args) -> int:
    import mvp  # 复用 .env 加载 + reasoning_effort/extra_body 逻辑

    if not mvp.OPENAI_API_KEY:
        print("OPENAI_API_KEY 未设置，跳过。")
        return 1
    print(f"[llm] {mvp.LLM_MODEL}"
          f"{' effort=' + mvp.LLM_REASONING_EFFORT if mvp.LLM_REASONING_EFFORT else ''}"
          f" @ {mvp.OPENAI_BASE_URL}")
    brain = mvp.Brain(os.getenv("ROLE", "后端工程师"), os.getenv("RESUME", ""))
    t0 = time.time()
    marks: dict[str, float] = {}
    out: list[str] = []

    def on_reason(_p: str) -> None:
        marks.setdefault("reason", time.time() - t0)

    def on_first() -> None:
        marks.setdefault("content", time.time() - t0)

    text = brain.answer(args.question, lambda p: out.append(p), on_reason=on_reason, on_first=on_first)
    print(f"[思考首字 {marks.get('reason', -1):.2f}s | 正文首字 {marks.get('content', -1):.2f}s "
          f"| 总计 {time.time()-t0:.2f}s]\n{text}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("deps").set_defaults(fn=cmd_deps)

    p = sub.add_parser("capture"); p.add_argument("-s", "--seconds", type=float, default=5.0)
    p.set_defaults(fn=cmd_capture)

    p = sub.add_parser("asr"); p.add_argument("-w", "--wav", required=True)
    p.set_defaults(fn=cmd_asr)

    p = sub.add_parser("e2e"); p.add_argument("-w", "--wav", required=True)
    p.set_defaults(fn=cmd_e2e)

    p = sub.add_parser("llm"); p.add_argument("-q", "--question", default="请做个自我介绍")
    p.set_defaults(fn=cmd_llm)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
