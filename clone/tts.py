"""语音播报（双机位笔试场景）：SAPI 读答案，屏幕完全不出字。

用 Windows 自带 SAPI（comtypes 调 SAPI.SpVoice），不额外装包；
默认中文声线（Huihui），可用 TTS_VOICE 指定；TTS_DEVICE 可指定输出设备描述关键字。
"""
from __future__ import annotations

import os
import queue
import re
import threading

SPF_ASYNC = 1
SPF_PURGE = 2


def clean_for_speech(text: str) -> str:
    """把 Markdown 答案改成能读的句子；长代码块不读，改成提示。"""
    t = text
    t = re.sub(r"```[a-zA-Z0-9+#-]*\n(.*?)```", lambda m: "\n代码部分请看屏幕。\n"
               if len(m.group(1)) > 80 else m.group(1) + "\n", t, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"[*_#>]+", "", t)
    t = re.sub(r"^\s*[-•]\s*", "", t, flags=re.M)
    t = re.sub(r"\n{2,}", "\n", t)
    return t.strip()


class Speaker(threading.Thread):
    def __init__(self, enabled: bool = True) -> None:
        super().__init__(daemon=True)
        self.enabled = enabled
        self.q: "queue.Queue[str | None]" = queue.Queue()
        self.voice = None
        self.error = ""
        self._stop = threading.Event()

    def run(self) -> None:
        try:
            import ctypes

            ctypes.windll.ole32.CoInitializeEx(None, 0x2)  # MTA，和采集线程保持一致
            import comtypes.client as cc

            v = cc.CreateObject("SAPI.SpVoice")
            want = os.getenv("TTS_VOICE", "Chinese")
            voices = v.GetVoices()
            for i in range(voices.Count):
                d = voices.Item(i).GetDescription()
                if want.lower() in d.lower() or (want == "Chinese" and "中文" in d):
                    v.Voice = voices.Item(i)
                    break
            dev = os.getenv("TTS_DEVICE", "").strip()
            if dev:
                outs = v.GetAudioOutputs()
                for i in range(outs.Count):
                    if dev.lower() in outs.Item(i).GetDescription().lower():
                        v.AudioOutput = outs.Item(i)
                        break
            v.Rate = int(os.getenv("TTS_RATE", "2"))
            v.Volume = int(os.getenv("TTS_VOLUME", "100"))
            self.voice = v
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            return
        while True:
            item = self.q.get()
            if item is None:
                break
            try:
                self.voice.Speak(item, SPF_ASYNC)
            except Exception as e:
                self.error = f"{type(e).__name__}: {e}"

    def speak(self, text: str) -> None:
        if not self.enabled or not text.strip():
            return
        if not self.is_alive() and self.error:
            return
        if not self.is_alive():
            self.start()
        self.q.put(clean_for_speech(text))

    def stop(self) -> None:
        if self.voice is not None:
            try:
                self.voice.Speak("", SPF_ASYNC | SPF_PURGE)
            except Exception:
                pass
        while True:
            try:
                self.q.get_nowait()
            except queue.Empty:
                break
