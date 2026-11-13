"""
面试侠同类最小可用原型（MVP）
链路: WASAPI loopback -> 16k 单声道 -> VAD 切句 -> ASR -> 问题判定 -> LLM 流式 -> 置顶透明窗

依赖: pip install -r requirements.txt
配置: 环境变量 OPENAI_BASE_URL / OPENAI_API_KEY / LLM_MODEL / ASR_MODEL

Windows 上 loopback 采集的是"系统正在播放的声音"，也就是会议里面试官的声音；
不需要虚拟声卡，也不会把自己的麦克风回灌进会议。
"""
from __future__ import annotations

import base64
import ctypes
import io
import os
import queue
import re
import sys
import threading
import time
import wave

import numpy as np

import hotkeys


def _quiet_unraisable(u) -> None:
    """comtypes 的 __del__ 在解释器退出时会拿已失效的 COM 指针 Release，
    报 OSError: access violation。它是「Exception ignored」，不影响功能，静音掉。"""
    exc = getattr(u, "exc_value", None)
    if isinstance(exc, OSError) and "access violation" in str(exc):
        return
    sys.__unraisablehook__(u)


sys.unraisablehook = _quiet_unraisable

# --- 崩溃取证：原生崩溃（0xC000041D）不会留 Python traceback，只能靠落盘的
# 最后一条轨迹判断死在哪一步。run.log 逐行 flush，用记事本看即可。
RUN_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.log")


def _trace(msg: str) -> None:
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')} [{os.getpid()}] {msg}\n")
    except Exception:
        pass


def _quiet_os_errors() -> None:
    """让 Windows 不要在崩溃时弹「python.exe 已停止工作 / 正在检查解决方案」。

    - SetErrorMode: 关掉硬错误弹窗和 GPF 对话框（只对本进程及其子进程生效）
    - HKCU\\...\\Windows Error Reporting\\DontShowUI=1: 关掉 WER 的 UI（当前用户）
    进程仍然会退出、仍然会写 run.log，只是不再弹窗打扰（屏幕共享时弹窗会露）。
    """
    try:
        k32 = ctypes.windll.kernel32
        k32.SetErrorMode(0x0001 | 0x0002 | 0x8000)  # FAILCRITICALERRORS|NOGPFAULTERRORBOX|NOOPENFILEERRORBOX
    except Exception:
        pass
    try:
        import winreg

        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Windows Error Reporting",
            0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
        )
        try:
            old, _ = winreg.QueryValueEx(key, "DontShowUI")
        except OSError:
            old = None
        if old != 1:
            winreg.SetValueEx(key, "DontShowUI", 0, winreg.REG_DWORD, 1)
            _trace("wer: DontShowUI 0->1（取消崩溃弹窗）")
        winreg.CloseKey(key)
    except Exception as e:
        _trace(f"wer: 设置失败 {type(e).__name__}: {e}")


_quiet_os_errors()


def _enable_faulthandler() -> None:
    """段错误/栈溢出这类信号能让 faulthandler 打出 Python 栈。"""
    try:
        import faulthandler

        _fh = open(RUN_LOG, "a", encoding="utf-8")
        faulthandler.enable(_fh, all_threads=True)
    except Exception:
        pass


def _install_excepthooks() -> None:
    """普通 Python 异常别把进程带走：写 run.log，主线程/Qt 继续跑。"""
    import traceback

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        try:
            _trace("EXC " + "".join(traceback.format_exception(exc_type, exc, tb))[-1200:])
        except Exception:
            pass

    def _thook(a):
        try:
            _trace("THREAD_EXC %s: %s" % (type(a.exc_value).__name__, a.exc_value))
        except Exception:
            pass

    sys.excepthook = _hook
    try:
        import threading as _th

        _th.excepthook = _thook
    except Exception:
        pass


def _ui_state_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_state.json")


def _load_ui_state() -> dict:
    try:
        import json

        with open(_ui_state_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save_ui_state(d: dict) -> None:
    try:
        import json

        tmp = _ui_state_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        os.replace(tmp, _ui_state_path())
    except Exception:
        pass


SHOW_PORT = int(os.getenv("SHOW_PORT", "19399") or 19399)


def _show_running() -> bool:
    """已有实例在跑，就让新进程通知它把窗口叫出来（双击 bat 即可找回隐藏的窗口）。"""
    import socket

    try:
        c = socket.create_connection(("127.0.0.1", SHOW_PORT), timeout=1.0)
        c.settimeout(1.5)
        c.sendall(b"show")
        ok = c.recv(16).strip() == b"msx"
        c.close()
        return ok
    except Exception:
        return False


class _ShowServer(threading.Thread):
    """本机回环端口做「叫出窗口」的入口，只接受 show，不监听外部。"""

    def __init__(self, ui):
        super().__init__(daemon=True)
        self.ui = ui

    def run(self) -> None:
        import socket

        srv = socket.socket()
        try:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            bound = False
            for _ in range(10):
                try:
                    srv.bind(("127.0.0.1", SHOW_PORT))
                    srv.listen(4)
                    bound = True
                    break
                except OSError:
                    time.sleep(0.3)
            if not bound:
                _trace(f"show server: port {SHOW_PORT} busy")
                return
            while True:
                c, _addr = srv.accept()
                try:
                    data = c.recv(32)
                    c.sendall(b"msx\n")
                    if data.strip() == b"show" and self.ui:
                        _trace("show server: show")
                        self.ui.show()
                except Exception:
                    pass
                finally:
                    try:
                        c.close()
                    except Exception:
                        pass
        except Exception as e:
            _trace(f"show server died {type(e).__name__}: {e}")



def _console_hwnd():
    """控制台窗口句柄（属于 conhost，本进程只能 ShowWindow/SetConsoleTitle，设不了 WDA）。"""
    try:
        import ctypes

        k32 = ctypes.windll.kernel32
        k32.GetConsoleWindow.restype = ctypes.c_void_p
        return k32.GetConsoleWindow() or None
    except Exception:
        return None


def _cloak_console() -> bool:
    """控制台窗口也设 WDA_EXCLUDEFROMCAPTURE（跨进程通常失败，保留兼容）。"""
    try:
        hwnd = _console_hwnd()
        if not hwnd:
            return False
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x11))
    except Exception:
        return False


def _console_setup(mode: str = "min", title: str = "Settings") -> str:
    """控制台的处置：hide（默认，任务栏和共享画面里都没有）/ min / show。
    最小化或隐藏后，用户仍可从任务栏点开看日志（hide 需要 Alt+Tab 或任务管理器）；
    关掉控制台 = 退出程序。"""
    try:
        import ctypes

        u = ctypes.windll.user32
        if title:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        hwnd = _console_hwnd()
        if not hwnd:
            return "no-console"
        if mode == "hide":
            u.ShowWindow(hwnd, 0)  # SW_HIDE：任务栏按钮消失，整屏共享拍不到
            return "hidden"
        if mode == "show":
            u.ShowWindow(hwnd, 5)  # SW_SHOW
            return "shown"
        u.ShowWindow(hwnd, 6)  # SW_MINIMIZE
        return "minimized"
    except Exception as e:
        return f"err:{e}"

SR = 16000
BLOCK = 1600  # 100ms
SILENCE_RMS = 0.006
SILENCE_HANG = 0.6  # 静音 600ms 断句
MIN_SPEECH = 0.5

# MODELS_DIR 在 _load_env() 之后再取，否则 .env 里的 MSX_MODELS_DIR 不生效


def _load_env() -> None:
    """读同目录 .env（存在才读），已存在的环境变量优先。"""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(p):
        return
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def resolve_asr_model(name: str) -> str:
    """把仓库名/Systran-xxx 映射到本地目录，避免每次联网。"""
    if os.path.isdir(name):
        return name
    tail = name.split("/")[-1]
    for cand in (tail, tail.replace("faster-whisper-", "")):
        p = os.path.join(MODELS_DIR, cand if cand.startswith("faster-whisper") else f"faster-whisper-{cand}")
        if os.path.isdir(p) and os.path.exists(os.path.join(p, "model.bin")):
            return p
    return name


_load_env()
MODELS_DIR = os.getenv("MSX_MODELS_DIR", r"E:\aaa_msx\models")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
VISION_MODEL = os.getenv("VISION_MODEL", "deepseek-v4.1-flash")
# 视觉模型同样是思考型，默认关思考：同一张题图 GLM 5.58s→1.53s，flash 0.83s
VISION_EXTRA_JSON = os.getenv("VISION_EXTRA_JSON", '{"thinking":{"type":"disabled"}}').strip()
ASR_MODEL = resolve_asr_model(os.getenv("ASR_MODEL", "faster-whisper-base"))

# 笔试模式：MODE=exam 时截图按笔试要求出答案（语言 / 力扣 or ACM）
MODE = os.getenv("MODE", "interview").strip().lower()
EXAM_LANG = os.getenv("EXAM_LANG", "自动识别")
EXAM_STYLE = os.getenv("EXAM_STYLE", "力扣（只写核心函数）")
# 伪装：共享内容列表里显示成普通窗口名；CLOAK=0 恢复真名
WIN_TITLE = os.getenv("WIN_TITLE", "Settings")
CLOAK = os.getenv("CLOAK", "1") not in ("0", "false", "False")
# 控制台窗口也做反截屏（日志本地可见，屏幕共享里看不见）
CLOAK_CONSOLE = os.getenv("CLOAK_CONSOLE", "1") not in ("0", "false", "False")
# 启动就把控制台最小化（最小化窗口不进屏幕共享；任务栏点开仍能看日志、关掉即退出）
CONSOLE_MIN = os.getenv("CONSOLE_MIN", "1") not in ("0", "false", "False")
# 更彻底：直接隐藏控制台窗口（任务栏按钮也消失，整屏共享看不到任何东西）。
# 隐藏后靠 Ctrl+Shift+Q 两下退出；要看日志就打开 clone\run.log。
CONSOLE_HIDE = os.getenv("CONSOLE_HIDE", "1") not in ("0", "false", "False")
CONSOLE_TITLE = os.getenv("CONSOLE_TITLE", WIN_TITLE)
# 托盘图标：整屏共享时通知区会露出来，默认关；想用托盘找回窗口就设 TRAY=1
TRAY = os.getenv("TRAY", "0") not in ("0", "false", "False")
# 双机位：语音播报（仅笔试）/ 手机联动
TTS_ON = os.getenv("TTS", "0") not in ("0", "false", "False")
MOBILE_ON = os.getenv("MOBILE", "0") not in ("0", "false", "False")
MOBILE_PORT = int(os.getenv("MOBILE_PORT", "8765"))
SHOT_MOUSE = os.getenv("SHOT_MOUSE", "1") not in ("0", "false", "False")
# 鼠标手势可配（对应官网「修饰键和点击方式可改」）
SHOT_CLICKS = int(os.getenv("SHOT_CLICKS", "2") or 2)
SHOT_BUTTON = os.getenv("SHOT_BUTTON", "left").strip().lower()
# 双击判定：两次点击的间隔上限（秒）与位置容差（像素）。Windows 默认双击速度是 500ms，
# 阈值定太小会导致手慢的"双击"识别不到（旧值 0.45s 就是这个坑）。
SHOT_INTERVAL = float(os.getenv("SHOT_INTERVAL", "0.85") or 0.85)
SHOT_DIST = int(os.getenv("SHOT_DIST", "24") or 24)
# 取图前把浮窗临时透明，避免截到自己（WDA 之外的双保险）
SHOT_HIDE_UI = os.getenv("SHOT_HIDE_UI", "1") not in ("0", "false", "False")
# 动作捕捉：扶眼镜 / 双击眨眼 触发截图（本机识别，画面不上传）
GESTURE_ON = os.getenv("GESTURE", "0") not in ("0", "false", "False")
# 长问句优化（实验，默认关）：宁可多等一句，也不在半句上抢答
LONG_Q = os.getenv("LONG_Q", "0") not in ("0", "false", "False")
# 手机联动时，第一题开始后把本机窗口藏起来（默认关，避免误以为程序挂了）
MOBILE_HIDE = os.getenv("MOBILE_HIDE", "0") not in ("0", "false", "False")
# 隐身保活：部分驱动/窗口重建会丢掉 WDA_EXCLUDEFROMCAPTURE，每 5 秒重设一次
STEALTH_KEEPALIVE = os.getenv("STEALTH_KEEPALIVE", "1") not in ("0", "false", "False")
# 隐身自检（秒，0=关）：临时解保护→截自己→判空白→恢复，确认 WDA 真的生效
STEALTH_SELFCHECK = float(os.getenv("STEALTH_SELFCHECK", "0") or 0)
# 笔试读题：CDP 真 DOM 优先（需要带 --remote-debugging-port 的浏览器），UIA 兜底
DOM_ON = os.getenv("DOM", "1") not in ("0", "false", "False")
# 自动读题：页面题干变化就自动作答（默认关，避免误答导航文本）
DOM_AUTO = os.getenv("DOM_AUTO", "0") not in ("0", "false", "False")
# 笔试安全模式：关摄像头/手机/语音，启动即隐藏窗口，F8 才显示
EXAM_SAFE = os.getenv("EXAM_SAFE", "0") not in ("0", "false", "False")
# 幽灵窗：平时不显示，答案到达才出现，N 秒后自动隐藏（防周期性全屏抓图）
EXAM_GHOST = os.getenv("EXAM_GHOST", "0") not in ("0", "false", "False")
GHOST_HIDE_AFTER = float(os.getenv("GHOST_HIDE_AFTER", "10") or 10)
EXAM_IDLE = os.getenv("EXAM_IDLE", "1") not in ("0", "false", "False")
EXAM_IDLE_HELP = """**笔试模式 · 快捷键**

窗口会一直显示，截图时自动隐身一下，抓完马上回来。
**退出：直接关掉黑色控制台窗口**（或 `Ctrl+Shift+Q` 连按两次）。
- `Shift+双击` 整屏看答案 ｜ `Alt+双击` 当前窗口
- `Shift+Alt+双击` 长截图（10 秒内按两次）
- 双击不好使就按键盘：`Ctrl+Shift+1` 整屏 ｜ `Ctrl+Shift+2` 窗口 ｜ `Ctrl+Shift+3` 长截图
- `Ctrl+Shift+S` 框选 ｜ `Ctrl+Shift+R` 重截
- `Ctrl+Shift+G` 重识别 ｜ `Ctrl+Shift+L` 题目列表
- `F8` 显隐 ｜ `F9` 点击穿透 ｜ 右下角「小」缩小、「隐」隐藏
- 鼠标拖动移动 ｜ 拖右下角改大小 ｜ `Ctrl+滚轮` 字号

> 共享/录屏里看不到这个窗口；截图瞬间自动隐身，不会把自己截进去。"""
EXAM_IDLE_MINI = """**笔试 · 迷你窗**
`Shift+双击` 整屏 ｜ `Alt+双击` 窗口 ｜ `Ctrl+Shift+S` 框选
`Ctrl+Shift+1/2/3` 键盘版整屏/窗口/长截图
`F8` 显隐 ｜ 点「小」还原 ｜ 关掉控制台即退出"""
if MODE == "exam" and EXAM_SAFE:
    # 笔试安全模式：不碰摄像头/端口/语音，答案窗口默认隐藏
    GESTURE_ON = False
    MOBILE_ON = False
    TTS_ON = False
# 默认输出被静音/音量 0 时 loopback 会全是 0 且不报错，启动时自动修一次
AUDIO_AUTOFIX = os.getenv("AUDIO_AUTOFIX", "1") not in ("0", "false", "False")

# 推理模型（deepseek-v4.1-flash / V4-Pro / GLM-5.3）默认先吐 reasoning_content，
# 正文要等思考结束才出来。effort 调低能明显缩短首字时间。
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "").strip()
LLM_EXTRA_JSON = os.getenv("LLM_EXTRA_JSON", "").strip()
# 回答模型档位（对齐官网「灵动 / 睿智」）：speed=先出字，natural=表达更自然但慢半拍。
# 显式写了 EFFORT/EXTRA 就以显式配置为准，这里只补默认值。
LLM_PROFILE = os.getenv("LLM_PROFILE", "speed").strip().lower()
if LLM_PROFILE == "natural" and not LLM_REASONING_EFFORT and not LLM_EXTRA_JSON:
    LLM_REASONING_EFFORT = "high"
# ⚡速答：先单独打一发很短的请求，答案出来前先给一句结论（官网同款交互）
QUICK_ANSWER = os.getenv("QUICK_ANSWER", "1") not in ("0", "false", "False")
# 早触发：说话过程中每 PARTIAL_STEP 秒识别一次，命中疑问词就先发 LLM，不等整句说完
PARTIAL_STEP = float(os.getenv("PARTIAL_STEP", "1.2"))
EARLY_ASK = os.getenv("EARLY_ASK", "1") not in ("0", "false", "False")
# 断句 hangover；SPEC_HANG 是在正式断句前先猜一次（静音 0.3s 就送 ASR），把 hangover 也重叠掉
HANG = float(os.getenv("SILENCE_HANG", "0.6"))
SPEC_HANG = float(os.getenv("SPEC_HANG", "0.3"))
if LONG_Q:  # 长问句优化：关掉早触发，并多等半拍，等面试官把限定条件说完
    EARLY_ASK = False
    HANG = max(HANG, 0.9)
# 回答风格：brief≈200字 / standard≈400字 / detailed≈800字 / outline≈300字要点
ANSWER_STYLE = os.getenv("ANSWER_STYLE", "standard").strip().lower()
STYLE_LEN = {
    "brief": ("极简", "不超过 120 字，只给结论和最关键的两点"),
    "standard": ("标准", "150-260 字，结论 + 两条要点或一个例子"),
    "detailed": ("详细", "400-600 字，结论 → 思路 → 具体案例，可以多展开"),
    "outline": ("大纲", "只给 3-5 条要点，每条一行，不展开"),
}
STYLE_NAME, STYLE_HINT = STYLE_LEN.get(ANSWER_STYLE, STYLE_LEN["standard"])
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", {"brief": 400, "standard": 800,
                                              "detailed": 1400, "outline": 500}.get(ANSWER_STYLE, 800)))

SYSTEM_PROMPT = """你是面试者的实时提词器。用户是{role}，简历要点：{resume}
规则：
- 第一人称、口语化、可直接念出来；不要复述问题，不要写"作为AI"。
- 先给一句结论，再给 2-3 个要点（能举例就举例）。
- 长度：{length}
- 问题若是英文，用中文回答，关键术语保留英文原样。
{translate}- 不要输出 Markdown 标题，口语里念不出来的符号一律不要。
{context}{addon}"""

TRANSLATE = os.getenv("TRANSLATE", "1") not in ("0", "false", "False")
TRANSLATE_HINT = ("- 英/日/韩等问题先给一行「【中文对照】<翻译>」，再按上面的规则作答。\n"
                  if TRANSLATE else "")

QUESTION_HINTS = (
    "吗", "呢", "什么", "怎么", "为什么", "如何", "哪", "谁", "多少", "几个",
    "介绍", "说说", "讲讲", "谈谈", "聊聊", "举例", "描述", "解释",
    "能不能", "可不可以", "是不是", "有没有", "会不会", "你觉得", "你认为", "请问",
)


def is_question(text: str) -> bool:
    t = text.strip()
    if len(t) < 4:
        return False
    if t.endswith(("？", "?")):
        return True
    return any(h in t for h in QUESTION_HINTS)


# Whisper 在静音/噪声上常见的臆造尾巴（initial_prompt 被回吐也算）
_HALLUCINATIONS = (
    "请用简体中文输出",
    "请不吝点赞",
    "订阅 转发",
    "字幕由",
    "amara.org",
    "中文字幕提供",
    "谢谢观看",
    "MBC 뉴스",
)


def _is_hallucination(text: str) -> bool:
    t = text.strip().strip("。，,.！!")
    if not t:
        return False
    if len(t) <= 24 and any(h in t for h in _HALLUCINATIONS):
        return True
    # 短片段被截断时 Whisper 会输出「请用一分钟ＧＧＧＧ…」这类单字刷屏
    if re.search(r"(.)\1{5,}", t):
        return True
    if len(t) >= 8 and len(set(t)) / len(t) < 0.4:
        return True
    return False


def _add_cuda_dlls() -> None:
    """ctranslate2 的 CUDA 版要 cublas64_12/cudnn64_9；pip 装的 nvidia-* 轮子不在 PATH 里。"""
    import glob

    roots = []
    try:
        import site

        roots += site.getsitepackages()
    except Exception:
        pass
    roots.append(os.path.join(sys.prefix, "Lib", "site-packages"))
    for r in roots:
        for d in glob.glob(os.path.join(r, "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(d)
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            except Exception:
                pass


def _coinit() -> None:
    """soundcard 在工作线程里要自己初始化 COM，否则默认输出设备枚举会报 0x800401f0。"""
    import ctypes

    try:
        ctypes.windll.ole32.CoInitializeEx(None, 0x2)
    except Exception:
        pass


def _resample(x: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or len(x) < 2:
        return x.astype(np.float32)
    n = int(round(len(x) * dst / src))
    return np.interp(np.linspace(0, 1, n, endpoint=False),
                     np.linspace(0, 1, len(x), endpoint=False), x).astype(np.float32)


def _normalize(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return (x * (peak / m)).astype(np.float32) if m > 1e-6 else x.astype(np.float32)


# ---------------------------------------------------------------- 音频采集
def _pick_speaker(sc):
    """AUDIO_DEVICE 可以写设备名的一部分（比如「耳机」「Headphones」「Realtek」），
    不写就用系统默认输出。选会议软件外放的那个设备才抓得到对方声音。"""
    want = os.getenv("AUDIO_DEVICE", "").strip().lower()
    if want:
        for s in sc.all_speakers():
            if want in s.name.lower():
                return s
        names = " / ".join(s.name for s in sc.all_speakers())
        print(f"[capture] 没找到名字含「{want}」的输出设备，用默认。可选：{names}", flush=True)
    return sc.default_speaker()


class LoopbackCapture(threading.Thread):
    """WASAPI loopback：抓"系统正在播放的声音"，即会议里对方的声音。"""

    def __init__(self, out_q: "queue.Queue[np.ndarray]"):
        super().__init__(daemon=True)
        self.q = out_q
        self.running = True
        self.device = ""

    def run(self) -> None:
        import soundcard as sc

        _coinit()
        spk = _pick_speaker(sc)
        self.device = spk.name
        silent_s, warned, tried_fallback = 0.0, False, False
        while self.running:
            # 必须用 speaker.id 解析：按名字解析会命中同名麦克风端点（id 前缀 0.0.1），录到的是话筒不是回环
            mic = sc.get_microphone(id=str(spk.id), include_loopback=True)
            switch = False
            try:
                with mic.recorder(samplerate=SR, channels=1, blocksize=BLOCK) as rec:
                    while self.running:
                        chunk = rec.record(numframes=BLOCK)[:, 0].astype(np.float32)
                        self.q.put(chunk)
                        # 长时间无信号：先提示，再自动回退到默认输出（对应官网「外放单路模式」）
                        peak = float(np.abs(chunk).max())
                        silent_s = silent_s + BLOCK / SR if peak < 0.01 else 0.0
                        if silent_s >= 8 and not warned:
                            warned = True
                            print("[capture] 已 8s 没采到声音：确认会议软件正在外放，"
                                  "且「音频设备」和会议的输出设备是同一个", flush=True)
                        if (silent_s >= 20 and not tried_fallback
                                and os.getenv("AUDIO_FALLBACK", "1") not in ("0", "false", "False")):
                            tried_fallback = True
                            alt = sc.default_speaker()
                            if str(alt.id) != str(spk.id):
                                print(f"[capture] 20s 无声音，回退到默认输出：{alt.name}", flush=True)
                                spk, self.device, silent_s, switch = alt, alt.name, 0.0, True
                                break
            except Exception as e:
                print(f"[capture] 16k 直采失败({type(e).__name__}: {e})，退 48k+重采样", flush=True)
                blocks = 4800
                with mic.recorder(samplerate=48000, channels=1, blocksize=blocks) as rec:
                    while self.running:
                        self.q.put(_resample(rec.record(numframes=blocks)[:, 0].astype(np.float32),
                                             48000, SR))
            if not switch:
                break



class VadSegmenter(threading.Thread):
    """能量 VAD + hangover 断句，输出 float32 语音段。"""

    def __init__(self, in_q: "queue.Queue[np.ndarray]", out_q: "queue.Queue[tuple[str, np.ndarray]]",
                 partial_step: float = PARTIAL_STEP, hang: float = HANG, spec_hang: float = SPEC_HANG):
        super().__init__(daemon=True)
        self.in_q = in_q
        self.out_q = out_q
        self.running = True
        self.noise = 0.002
        self.partial_step = partial_step
        self.hang = hang
        self.spec_hang = spec_hang

    def run(self) -> None:
        buf: list[np.ndarray] = []
        speech_s = 0.0
        silence_s = 0.0
        since_partial = 0.0
        speculated = False
        while self.running:
            try:
                blk = self.in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(blk ** 2)) + 1e-9)
            if rms < self.noise * 1.5:
                self.noise = 0.98 * self.noise + 0.02 * rms
            voiced = rms > max(SILENCE_RMS, self.noise * 2.5)

            if voiced:
                buf.append(blk)
                speech_s += len(blk) / SR
                silence_s = 0.0
                speculated = False
                since_partial += len(blk) / SR
                # 边说边识别：只发中间态，worker 命中疑问词就提前调 LLM
                if self.partial_step > 0 and speech_s >= 1.0 and since_partial >= self.partial_step:
                    since_partial = 0.0
                    self.out_q.put(("partial", np.concatenate(buf)))
            elif buf:
                buf.append(blk)
                silence_s += len(blk) / SR
                # 静音 0.3s 先猜一把，0.6s 才正式断句——把 hangover 也重叠进 ASR/LLM 里
                if not speculated and self.spec_hang < self.hang and silence_s >= self.spec_hang \
                        and speech_s >= MIN_SPEECH:
                    speculated = True
                    self.out_q.put(("spec", np.concatenate(buf)))
                if silence_s >= self.hang:
                    if speech_s >= MIN_SPEECH:
                        self.out_q.put(("final", np.concatenate(buf)))
                    buf, speech_s, silence_s, since_partial, speculated = [], 0.0, 0.0, 0.0, False


# ---------------------------------------------------------------- ASR
def _wav_bytes(pcm: np.ndarray) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(pcm, -1, 1) * 32767).astype("<i2").tobytes())
    return bio.getvalue()


class Asr:
    """优先本地 faster-whisper；没装则走 OpenAI 兼容的 /audio/transcriptions。"""

    def __init__(self) -> None:
        self.local = None
        self.mode = ""
        try:
            _add_cuda_dlls()
            from faster_whisper import WhisperModel  # type: ignore

            dims = ["cuda", "cpu"] if self._cuda() else ["cpu"]
            last = None
            for dev in dims:
                try:
                    m = WhisperModel(
                        ASR_MODEL, device=dev,
                        compute_type="float16" if dev == "cuda" else "int8")
                    if dev == "cuda":  # 缺 cublas/cudnn 时构造成功但推理才炸，先试跑 1s 静音
                        list(m.transcribe(np.zeros(SR, dtype=np.float32), language="zh",
                                          beam_size=1)[0])
                    self.local = m
                    self.mode = f"local:{os.path.basename(ASR_MODEL) or ASR_MODEL}@{dev}"
                    break
                except Exception as e:  # 缺 cublas/cudnn 时回退 CPU
                    last = e
                    print(f"[asr] {dev} 初始化失败({type(e).__name__}: {e})", flush=True)
            if self.local is None:
                raise last or RuntimeError("no device")
        except Exception as e:
            print(f"[asr] 本地模型不可用({type(e).__name__}: {e})，改用云端转写", flush=True)
            from openai import OpenAI

            self.client = OpenAI(base_url=os.getenv("ASR_BASE_URL", OPENAI_BASE_URL),
                                 api_key=OPENAI_API_KEY)
            self.mode = "cloud"

    @staticmethod
    def _cuda() -> bool:
        try:
            import ctranslate2  # type: ignore

            return ctranslate2.get_cuda_device_count() > 0
        except Exception:
            return False

    def transcribe(self, pcm: np.ndarray) -> str:
        if self.local is not None:
            peak = float(np.max(np.abs(pcm))) if len(pcm) else 0.0
            if 0 < peak < 0.35:  # 系统音量偏小，先归一化，Whisper 对低电平不敏感会漏字
                pcm = _normalize(pcm, 0.9)
            segs, _ = self.local.transcribe(
                pcm, language="zh", beam_size=1, vad_filter=False,
                initial_prompt="以下是普通话面试对话，请用简体中文输出。",
            )
            parts = []
            for s in segs:
                # 静音/噪声段 Whisper 会编出「请用简体中文输出」这类尾巴，用概率丢掉
                nsp = getattr(s, "no_speech_prob", 0.0)
                alp = getattr(s, "avg_logprob", 0.0)
                if nsp > 0.55:
                    continue
                if alp < -1.1:
                    continue
                parts.append(s.text)
            text = "".join(parts).strip()
            return "" if _is_hallucination(text) else text
        raw = _wav_bytes(pcm)
        r = self.client.audio.transcriptions.create(
            model=os.getenv("ASR_API_MODEL", "FunAudioLLM/SenseVoiceSmall"),
            file=("a.wav", raw, "audio/wav"),
            language="zh",
        )
        return (getattr(r, "text", "") or "").strip()


# ---------------------------------------------------------------- LLM
class Brain:
    def __init__(self, role: str = "后端工程师", resume: str = "",
                 context: str = "", addon: str = "") -> None:
        self.client = None
        if OPENAI_API_KEY:
            from openai import OpenAI

            self.client = OpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)
        self.system = SYSTEM_PROMPT.format(role=role, resume=resume or "（未提供）",
                                           length=STYLE_HINT, translate=TRANSLATE_HINT,
                                           context=("\n" + context) if context else "",
                                           addon=addon or "")
        self.history: list[dict] = []
        self.last_used = 0.0
        self.extra: dict = {}
        if LLM_EXTRA_JSON:
            import json

            try:
                self.extra = json.loads(LLM_EXTRA_JSON)
            except Exception as e:
                print(f"[llm] LLM_EXTRA_JSON 解析失败({e})，忽略", flush=True)

    def _stream(self, kwargs: dict, on_delta, on_reason, on_first, cancel=None) -> str:
        acc: list[str] = []
        first = [on_first]
        stream = self.client.chat.completions.create(**kwargs)
        try:
            for chunk in stream:
                if cancel is not None and cancel.is_set():
                    break
                if not chunk.choices:
                    continue
                d = chunk.choices[0].delta
                # 推理模型会先流 reasoning_content（部分网关叫 reasoning），正文在后面
                reason = getattr(d, "reasoning_content", None) or getattr(d, "reasoning", None)
                if reason and on_reason:
                    on_reason(reason)
                piece = d.content or ""
                if piece:
                    if first[0]:
                        first[0]()
                        first[0] = None
                    acc.append(piece)
                    on_delta(piece)
        finally:
            try:
                stream.close()
            except Exception:
                pass
        return "".join(acc)

    def answer(self, question: str, on_delta, on_reason=None, on_first=None, cancel=None) -> str:
        if self.client is None:
            raise RuntimeError("未配置 OPENAI_API_KEY（复制 .env.example 为 .env 并填写）")
        self.history.append({"role": "user", "content": question})
        msgs = [{"role": "system", "content": self.system}] + self.history[-6:]
        kwargs: dict = dict(model=LLM_MODEL, messages=msgs, stream=True,
                            temperature=0.6, max_tokens=MAX_TOKENS)
        if LLM_REASONING_EFFORT:
            kwargs["reasoning_effort"] = LLM_REASONING_EFFORT
        try:
            if self.extra:
                try:
                    text = self._stream({**kwargs, "extra_body": self.extra}, on_delta, on_reason,
                                        on_first, cancel)
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    # 不同网关对 extra_body 的容忍度不一样，被拒就退回默认模式，别让整句答案丢掉
                    if any(k in msg.lower() for k in ("400", "invalid", "unknown", "unsupported", "unrecognized")):
                        print(f"[llm] extra 参数被拒（{msg[:100]}），本次退回默认模式", flush=True)
                        self.extra = {}
                        text = self._stream(kwargs, on_delta, on_reason, on_first, cancel)
                    else:
                        raise
            else:
                text = self._stream(kwargs, on_delta, on_reason, on_first, cancel)
        except Exception:
            self.history.pop()  # 失败别把半句话留在上下文里
            raise
        text = text.strip()
        self.history.append({"role": "assistant", "content": text})
        self.last_used = time.time()
        return text

    def answer_image(self, png: bytes, prompt: str, on_delta, on_first=None, cancel=None) -> str:
        """截图识别：图片走 data URL，模型用 VISION_MODEL（relay 上 GLM-5.3 实测可读中英混排）。"""
        if self.client is None:
            raise RuntimeError("未配置 OPENAI_API_KEY")
        b64 = base64.b64encode(png).decode()
        # 按字节头判定格式（prepare() 可能已转 JPEG，data URL 的 mime 必须匹配）
        if png[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif png[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        else:
            mime = "image/png"
        allow_extra = VISION_EXTRA_JSON
        messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64," + b64}},
            ]},
        ]
        kwargs: dict = dict(model=VISION_MODEL, messages=messages, stream=True,
                            temperature=0.3, max_tokens=1800)
        if allow_extra:
            import json

            try:
                kwargs["extra_body"] = json.loads(allow_extra)
            except Exception:
                pass
        text = self._stream(kwargs, on_delta, None, on_first, cancel).strip()
        # 图片不进上下文（太大），只留一句占位，方便“报错再截一次”继续追问
        self.history.append({"role": "user", "content": "（上一轮是截图提问）"})
        self.history.append({"role": "assistant", "content": text})
        self.last_used = time.time()
        return text

    def warm_vision(self, quiet: bool = False) -> None:
        """把视觉模型/连接焐热：64x64 白图 + 最短请求，拿到首 token 就断。"""
        if self.client is None:
            return
        t0 = time.time()
        try:
            import io as _io

            try:
                from PIL import Image
                im = Image.new("RGB", (64, 64), (255, 255, 255))
                bio = _io.BytesIO()
                im.save(bio, format="PNG")
                b64 = base64.b64encode(bio.getvalue()).decode()
            except Exception:
                b64 = ""
            messages = [
                {"role": "system", "content": "你是一个读图助手。"},
                {"role": "user", "content": [
                    {"type": "text", "text": "在吗"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + b64}},
                ]},
            ]
            kwargs: dict = dict(model=VISION_MODEL, messages=messages, stream=True,
                                temperature=0, max_tokens=1)
            if VISION_EXTRA_JSON:
                import json as _json
                try:
                    kwargs["extra_body"] = _json.loads(VISION_EXTRA_JSON)
                except Exception:
                    pass
            stream = self.client.chat.completions.create(**kwargs)
            for _chunk in stream:
                break
            stream.close()
            if not quiet:
                print(f"[llm] 视觉预热完成 {time.time() - t0:.2f}s", flush=True)
        except Exception as e:
            if not quiet:
                print(f"[llm] 视觉预热失败 {type(e).__name__}: {e}", flush=True)

    def quick(self, question: str) -> str:
        """⚡速答：只要一句话结论。独立请求、不写 history，避免污染正式答案的上下文。"""
        if self.client is None:
            return ""
        kw: dict = dict(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你在帮面试者答题。第一人称，只给一句话结论，40 字以内，直接回答，不要自我介绍，不要解释。"},
                {"role": "user", "content": question},
            ],
            temperature=0.3, max_tokens=200, stream=False,
        )
        if LLM_REASONING_EFFORT:
            kw["reasoning_effort"] = LLM_REASONING_EFFORT
        for use_extra in ((True, False) if self.extra else (False,)):
            try:
                k = dict(kw)
                if use_extra:
                    k["extra_body"] = self.extra
                r = self.client.chat.completions.create(**k)
                return (r.choices[0].message.content or "").strip()
            except Exception:
                continue
        return ""

    def supplement(self, question: str, answer: str = "", n: int = 3) -> str:
        """追问预判：给出面试官最可能追问的 n 个问题 + 一句回答要点。不写 history。"""
        if self.client is None:
            return ""
        prompt = (
            f"面试官的问题：{question}\n\n我已经给出的回答：{answer[:1200] or '（还没答）'}\n\n"
            f"请列出面试官最可能继续追问的 {n} 个问题，每个问题下面给一句 40 字以内的回答要点。"
            "格式：\n1. 追问问题\n   答：要点\n不要寒暄，不要总结。"
        )
        kw: dict = dict(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "你是面试教练，擅长预判面试官的追问。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4, max_tokens=600, stream=False,
        )
        if LLM_REASONING_EFFORT:
            kw["reasoning_effort"] = LLM_REASONING_EFFORT
        for use_extra in ((True, False) if self.extra else (False,)):
            try:
                k = dict(kw)
                if use_extra:
                    k["extra_body"] = self.extra
                r = self.client.chat.completions.create(**k)
                return (r.choices[0].message.content or "").strip()
            except Exception:
                continue
        return ""

    def warm(self, quiet: bool = False) -> None:
        """启动/空闲时先打一发最短请求，把连接/前缀缓存焐热；拿到第一个 token 立刻断开。"""
        if self.client is None:
            return
        t0 = time.time()
        try:
            kwargs: dict = dict(model=LLM_MODEL, messages=[
                {"role": "system", "content": self.system},
                {"role": "user", "content": "在吗"},
            ], stream=True, max_tokens=1, temperature=0)
            if self.extra:
                kwargs["extra_body"] = self.extra
            stream = self.client.chat.completions.create(**kwargs)
            for _chunk in stream:
                break
            stream.close()
            self.last_used = time.time()
            if not quiet:
                print(f"[llm] 预热完成 {time.time() - t0:.2f}s", flush=True)
        except Exception as e:
            if not quiet:
                print(f"[llm] 预热失败（不影响主流程）: {type(e).__name__}: {e}", flush=True)


# ---------------------------------------------------------------- 界面
WDA_EXCLUDEFROMCAPTURE = 0x11
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080

# 小窗样式预设（对应官网「极暗低调 / 护眼蓝灰 / 大字清晰」）
THEMES = {
    "dark": {"bg": "rgba(16,17,20,216)", "fg": "#eaeaea", "code_bg": "#1b2028",
             "inline_bg": "#1d2430", "font": 15, "code_px": 13, "label": "极暗低调"},
    "blue": {"bg": "rgba(22,30,42,222)", "fg": "#dbe6f2", "code_bg": "#16202c",
             "inline_bg": "#1b2836", "font": 15, "code_px": 13, "label": "护眼蓝灰"},
    "large": {"bg": "rgba(10,10,12,232)", "fg": "#ffffff", "code_bg": "#1b2028",
              "inline_bg": "#232a36", "font": 19, "code_px": 16, "label": "大字清晰"},
}
THEME_ORDER = ["dark", "blue", "large"]
THEME = os.getenv("THEME", "dark")


_ANS_TAG = re.compile(r"^【答案】\s*")
_EXP_TAG = re.compile(r"^【解析】\s*")


def _md_html(text: str, code_px: int = 13, code_bg: str = "#1b2028",
             inline_bg: str = "#1d2430") -> str:
    """极简 Markdown → HTML：代码块/行内代码/换行 + 答案/解析分色。够答案展示用。"""
    import html as _h

    out, in_code, code = [], False, []
    for line in (text or "").split("\n"):
        if line.strip().startswith("```"):
            if in_code:
                out.append(f'<pre style="background:{code_bg};padding:8px;border-radius:6px;'
                           f'font-family:Consolas;font-size:{code_px}px;white-space:pre-wrap">'
                           + _h.escape("\n".join(code)) + "</pre>")
                code, in_code = [], False
            else:
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        s = _h.escape(line)
        s = re.sub(r"`([^`]+)`", rf'<code style="background:{inline_bg};padding:1px 4px;border-radius:4px">\1</code>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"^#{1,6}\s*", "", s)  # 去掉行首 Markdown 标题符，避免误触发浏览器标题语义
        s = re.sub(r"^[-*]\s+", "· ", s)   # 列表符换成圆点，别显示成横杠
        if s.startswith("&gt;"):
            s = re.sub(r"^&gt;\s*", "", s)
            out.append('<div style="color:#9aa4b2;font-size:0.92em;margin:6px 0">'
                       + s + "</div>")
            continue
        if _ANS_TAG.match(s):
            s = _ANS_TAG.sub("", s)
            out.append('<div style="background:rgba(56,189,248,0.15);border-left:3px solid #38bdf8;'
                       'padding:6px 8px;border-radius:5px;margin:4px 0;font-size:1.06em;'
                       f'font-weight:600;color:#9fe6ff">{s}</div>')
            continue
        if _EXP_TAG.match(s):
            s = _EXP_TAG.sub("", s)
            out.append('<div style="color:#c2cbd6;border-left:2px solid rgba(194,203,214,0.4);'
                       f'padding:2px 8px;margin:2px 0;font-size:0.94em">{s}</div>')
            continue
        out.append(s)
    if in_code:
        out.append(f'<pre style="background:{code_bg};padding:8px;border-radius:6px;'
                   f'font-family:Consolas;font-size:{code_px}px;white-space:pre-wrap">'
                   + _h.escape("\n".join(code)) + "</pre>")
    body = "<br>".join(out)
    # 答案/解析是块级 div，别让前后的 <br> 撑出空行
    body = body.replace("<br><div", "<div").replace("</div><br>", "</div>")
    return "<div style='line-height:1.55'>" + body + "</div>"


class Overlay:
    """无边框置顶透明窗；WDA_EXCLUDEFROMCAPTURE 让它在录屏/共享里消失。

    伪装：窗口标题默认 "Settings"，WS_EX_TOOLWINDOW 不进任务栏 / Alt-Tab。
    """

    def __init__(self) -> None:
        self.qt = None
        self.win = None
        self.app = None
        self.click_through = False
        self.opacity = 0.96
        self.history: list[dict] = []
        self.idx = -1
        self.pinned = False
        self.scale = 1.0
        self.compact = False
        self._last_text = ""
        self._last_render = 0.0
        self._list_open = False
        self._ghost_timer = None
        self._ghost_thread = None
        self._was_visible = True
        if "--no-ui" in sys.argv:
            self._log("--no-ui：只输出到控制台")
            return
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
        except ImportError:
            self._log("未安装 PySide6，降级为控制台输出")
            return
        self.QtCore, self.QtGui, self.QtWidgets = QtCore, QtGui, QtWidgets

        self.app = QtWidgets.QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.win = QtWidgets.QWidget()
        self.win.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool
        )
        self.win.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        # 关键：无边框 + 半透明窗体下 QSS 背景经常压根不画（实测 win.grab 全透明），
        # 现场表现就是「只有白字浮在壁纸上」。直接自己画一块圆角底板，稳。
        self.win.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.win.paintEvent = self._paint_panel
        self._bg = (16, 17, 20, 216)
        self.win.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.win.setWindowTitle(WIN_TITLE)
        self.theme = THEME if THEME in THEMES else "dark"
        self.win.setStyleSheet("QWidget{background:rgba(16,17,20,216);border-radius:10px}")

        self.view = QtWidgets.QTextBrowser(self.win)
        self.view.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.view.setOpenLinks(False)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet(
            "QTextBrowser{background:transparent;border:none;color:#eaeaea;"
            "font:15px 'Microsoft YaHei';padding:10px 14px}")
        self.status = QtWidgets.QLabel("就绪", self.win)
        self.status.setStyleSheet("color:#7d8590;font:11px 'Microsoft YaHei';background:transparent")
        self.compact = False
        bar = QtWidgets.QWidget(self.win)
        self._bar = bar
        hb = QtWidgets.QHBoxLayout(bar)
        hb.setContentsMargins(14, 0, 8, 6)
        hb.setSpacing(6)
        hb.addWidget(self.status, 1)
        btn_css = ("QPushButton{background:rgba(125,133,144,40);color:#c8d0da;border:none;"
                   "border-radius:4px;font:11px 'Microsoft YaHei'}"
                   "QPushButton:hover{background:rgba(125,133,144,90)}")
        self.btn_small = QtWidgets.QPushButton("小", bar)
        self.btn_small.setToolTip("缩小/还原窗口")
        self.btn_hide = QtWidgets.QPushButton("隐", bar)
        self.btn_hide.setToolTip("隐藏窗口（F8 再叫出）")
        for _b in (self.btn_small, self.btn_hide):
            _b.setFixedSize(24, 18)
            _b.setCursor(QtCore.Qt.PointingHandCursor)
            _b.setStyleSheet(btn_css)
            _b.setFocusPolicy(QtCore.Qt.NoFocus)
            hb.addWidget(_b, 0)
        self.btn_small.clicked.connect(self.toggle_compact)
        self.btn_hide.clicked.connect(self.hide)
        # 识别回显：截到的图缩略图，确认没截错
        self.thumb = QtWidgets.QLabel(self.win)
        self.thumb.setStyleSheet("background:transparent;padding:2px 14px 0 14px")
        self.thumb.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self.thumb.setVisible(False)
        self._apply_theme(self.theme)
        self._log(f"样式：{THEMES[self.theme]['label']}（Ctrl+Alt+Y 切换）")

        lay = QtWidgets.QVBoxLayout(self.win)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(self.thumb, 0)
        lay.addWidget(self._bar, 0)
        self.win.resize(800, 620)
        self._place_top_right()
        self._restore_geometry()
        self._state_timer = QtCore.QTimer()
        self._state_timer.setInterval(10000)
        self._state_timer.timeout.connect(self._save_geometry)
        self._state_timer.start()

        Bridge = type("Bridge", (QtCore.QObject,), {
            "status": QtCore.Signal(str),
            "answer": QtCore.Signal(str),
            "pick": QtCore.Signal(),
            "thumb": QtCore.Signal(object),
            "grid": QtCore.Signal(),
            "toggle": QtCore.Signal(),
            "show_req": QtCore.Signal(),
            "hide_req": QtCore.Signal(),
            "grab_hide_req": QtCore.Signal(),
            "grab_show_req": QtCore.Signal(),
            "hotkey": QtCore.Signal(str),
        })
        self.bridge = Bridge()
        self.bridge.status.connect(self._set_status_main)
        self.bridge.answer.connect(self._render_main)
        self.bridge.pick.connect(self._pick_main)
        self.bridge.thumb.connect(self._set_thumb_main)
        self.bridge.grid.connect(self._grid_main)
        self.bridge.toggle.connect(self._toggle_main)
        self.bridge.show_req.connect(self._show_main)
        self.bridge.hide_req.connect(self._hide_main)
        self.bridge.grab_hide_req.connect(self._grab_hide_main)
        self.bridge.grab_show_req.connect(self._grab_show_main)
        self.bridge.hotkey.connect(self._hotkey_main)
        self._hk_fns = {}
        self._grab_evt = threading.Event()
        self._was_visible = True
        self._pick_cb = [None]
        self._stealth_state = None
        if STEALTH_KEEPALIVE:
            # 官方同款：隐身状态 5 秒保活（驱动/窗口重建可能悄悄丢掉 WDA）
            self._stealth_timer = QtCore.QTimer()
            self._stealth_timer.setInterval(5000)
            self._stealth_timer.timeout.connect(self._stealth_main)
            self._stealth_timer.start()
            QtCore.QTimer.singleShot(0, self._stealth_main)
        if STEALTH_SELFCHECK > 0:
            self._check_timer = QtCore.QTimer()
            self._check_timer.setInterval(int(STEALTH_SELFCHECK * 1000))
            self._check_timer.timeout.connect(self._stealth_selfcheck)
            self._check_timer.start()
        self._grid = None

        self._drag = None
        self._rsz = None
        self.win.mousePressEvent = self._press
        self.win.mouseMoveEvent = self._move
        self.win.mouseReleaseEvent = self._release
        # QTextBrowser 铺满整窗并吃掉鼠标事件，窗口自身的 mousePress 永远不会触发，
        # 所以拖动/缩放要在子控件（含 viewport）上用事件过滤器接。
        # Overlay 不是 QObject，事件过滤器得套一层。
        _ov = self

        class _Filt(QtCore.QObject):
            def eventFilter(_s, obj, ev):
                return _ov.eventFilter(obj, ev)

        self._filt = _Filt(self.win)
        for _w in (self.view, self.view.viewport(), self.status, self._bar, self.thumb):
            _w.setMouseTracking(True)
            _w.installEventFilter(self._filt)

        hwnd = int(self.win.winId())
        self._cloak(hwnd)
        ok = self._wda(hwnd)
        self._log(f"WDA_EXCLUDEFROMCAPTURE = {ok}")
        self._tray() if TRAY else None
        self.win.show()
        self.qt = QtCore

    def _paint_panel(self, _ev):
        """自己画深色圆角底板：QSS 在无边框半透明顶层窗口上不可靠。"""
        if not self.qt:
            return
        Q = self.QtCore
        p = self.QtGui.QPainter(self.win)
        p.setRenderHint(self.QtGui.QPainter.Antialiasing, True)
        r, g, b, a = self._bg
        p.setBrush(self.QtGui.QColor(r, g, b, a))
        p.setPen(Q.Qt.NoPen)
        rr = self.win.rect().adjusted(0, 0, -1, -1)
        p.drawRoundedRect(rr, 10, 10)
        p.end()

    def _apply_theme(self, name: str) -> None:
        t = THEMES.get(name) or THEMES["dark"]
        self.theme = name if name in THEMES else "dark"
        m = re.search(r"rgba?\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d+))?\)", t["bg"])
        if m:
            self._bg = (int(m.group(1)), int(m.group(2)), int(m.group(3)),
                        int(m.group(4) or 255))
        fpx = max(11, int(round((t["font"] - (2 if self.compact else 0)) * self.scale)))
        self.win.setStyleSheet(
            f"QWidget{{background:{t['bg']};border-radius:10px}}")
        self.view.setStyleSheet(
            f"QTextBrowser{{background:transparent;border:none;color:{t['fg']};"
            f"font:{fpx}px 'Microsoft YaHei';padding:10px 14px}}")
        if self.history and 0 <= self.idx < len(self.history):
            self._render_main(self.history[self.idx]["a"] or "")

    def cycle_theme(self) -> None:
        if not self.qt:
            return
        i = THEME_ORDER.index(self.theme) if self.theme in THEME_ORDER else 0
        nxt = THEME_ORDER[(i + 1) % len(THEME_ORDER)]
        self._apply_theme(nxt)
        self.set_status(f"样式：{THEMES[nxt]['label']}")

    def _place_top_right(self) -> None:
        s = self.app.primaryScreen().availableGeometry()
        self.win.move(s.right() - self.win.width() - 40, s.top() + 40)

    def _restore_geometry(self) -> None:
        """崩溃/重启后回到上次的位置和大小（自愈的一部分，不用重新摆窗口）。"""
        QtCore = self.QtCore
        d = _load_ui_state()
        try:
            w, h = int(d.get("w", 0)), int(d.get("h", 0))
            x, y = int(d.get("x", 0)), int(d.get("y", 0))
        except Exception:
            return
        if w >= 560 and h >= 400:
            self.win.resize(w, h)
        if self.app.screenAt(QtCore.QPoint(x + 20, y + 20)):
            self.win.move(x, y)

    def _save_geometry(self) -> None:
        try:
            if not self.win:
                return
            g = self.win.geometry()
            _save_ui_state({"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()})
        except Exception:
            pass

    # ---- 截图时不把自己截进去 ----
    def grab_hide(self) -> None:
        """任意线程可调（截图钩子线程会调）。

        以前直接 win.hide()：从非 GUI 线程碰 QWidget 会让 Qt 在原生回调里
        抛异常，进程以 0xC000041D（STATUS_FATAL_USER_CALLBACK_EXCEPTION）
        直接消失。改成信号切回主线程，并阻塞等隐藏真正生效再开始抓图。
        """
        if not self.win:
            return
        try:
            same = self.QtCore.QThread.currentThread() is self.app.thread()
        except Exception:
            same = True
        if not same:
            self._grab_evt.clear()
            self.bridge.grab_hide_req.emit()
            self._grab_evt.wait(0.8)
            return
        self._grab_hide_main()

    def _grab_hide_main(self) -> None:
        _trace("grab_hide enter")
        if self.win:
            self._was_visible = bool(self.win.isVisible())
            if self._was_visible:
                self.win.hide()
                try:
                    self.app.processEvents()
                except Exception:
                    pass
        self._grab_evt.set()

    def grab_show(self) -> None:
        if not self.win:
            return
        try:
            same = self.QtCore.QThread.currentThread() is self.app.thread()
        except Exception:
            same = True
        if not same:
            self.bridge.grab_show_req.emit()
            return
        self._grab_show_main()

    def _grab_show_main(self) -> None:
        _trace("grab_show enter")
        if self.win:
            # 截图前是什么状态就恢复什么状态：常驻可见→回来；幽灵窗未出现→保持隐藏
            if getattr(self, "_was_visible", True):
                self.win.setWindowOpacity(self.opacity)
                self.win.show()
            try:
                self.win.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
            except Exception:
                pass
        self._grab_evt.set()

    # ---- 框选截图区域（Ctrl+Shift+S） ----
    def request_region(self, cb) -> None:
        """任意线程可调；切回 Qt 主线程再弹框选层。"""
        if not self.qt:
            return
        self._pick_cb[0] = cb
        self.bridge.pick.emit()

    def _pick_main(self) -> None:
        cb = self._pick_cb[0]
        self._pick_cb[0] = None
        if cb:
            self.pick_region(cb)

    def pick_region(self, cb) -> None:
        if not self.qt:
            return
        QtCore, QtGui, QtWidgets = self.QtCore, self.QtGui, self.QtWidgets
        geo = QtCore.QRect()
        for s in self.app.screens():
            geo = geo.united(s.geometry())

        sel = QtWidgets.QWidget(None, QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool
                                | QtCore.Qt.WindowStaysOnTopHint
                                | QtCore.Qt.WindowDoesNotAcceptFocus)
        sel.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        sel.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        sel.setGeometry(geo)
        sel.setCursor(QtCore.Qt.CrossCursor)
        st = {"o": None, "r": QtCore.QRect()}

        def paint(_ev):
            p = QtGui.QPainter(sel)
            p.fillRect(sel.rect(), QtGui.QColor(0, 0, 0, 100))
            r = st["r"]
            if r and not r.isNull():
                p.setCompositionMode(QtGui.QPainter.CompositionMode_Clear)
                p.fillRect(r, QtCore.Qt.transparent)
                p.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)
                p.setPen(QtGui.QPen(QtGui.QColor(90, 170, 255), 2))
                p.drawRect(r)
                p.setPen(QtGui.QColor(230, 240, 255))
                p.setFont(QtGui.QFont("Microsoft YaHei", 11))
                p.drawText(r.adjusted(6, 6, -6, -6), QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop,
                           f"{r.width()}×{r.height()}")
            p.setPen(QtGui.QColor(205, 215, 230))
            p.setFont(QtGui.QFont("Microsoft YaHei", 13))
            p.drawText(sel.rect().adjusted(0, 26, 0, 0), QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop,
                       "拖动框选题目区域 · Esc 取消")
            p.end()

        def press(ev):
            st["o"] = ev.position().toPoint()
            st["r"] = QtCore.QRect(st["o"], QtCore.QSize())
            sel.update()

        def move(ev):
            if st["o"] is None:
                return
            st["r"] = QtCore.QRect(st["o"], ev.position().toPoint()).normalized()
            sel.update()

        def release(_ev):
            r = st["r"]
            sel.close()
            if not r or r.width() < 24 or r.height() < 16:
                self.set_status("区域太小，已取消")
                return
            g = QtCore.QRect(r)
            g.translate(geo.topLeft())
            # Qt 坐标是逻辑像素，ImageGrab 用物理像素 → 按所在屏幕 DPR 换算
            ratio = 1.0
            try:
                s = self.app.screenAt(QtCore.QPoint(g.center()))
                if s is not None:
                    ratio = float(s.devicePixelRatio())
            except Exception:
                pass
            cb((int(g.left() * ratio), int(g.top() * ratio),
                int((g.right() + 1) * ratio), int((g.bottom() + 1) * ratio)))

        def key(ev):
            if ev.key() == QtCore.Qt.Key_Escape:
                sel.close()

        def rclick(_ev):
            sel.close()

        sel.paintEvent = paint
        sel.mousePressEvent = press
        sel.mouseMoveEvent = move
        sel.mouseReleaseEvent = release
        sel.keyPressEvent = key
        sel.mousePressEvent = lambda ev: (rclick(ev) if ev.button() == QtCore.Qt.RightButton else press(ev))
        sel.show()
        sel.raise_()
        # 框选层也不出现在共享画面里；且不抢焦点（不触发平台的切屏判定）
        try:
            import ctypes

            ctypes.windll.user32.SetWindowDisplayAffinity(int(sel.winId()), 0x11)
        except Exception:
            pass

    def _cloak(self, hwnd: int) -> None:
        import ctypes

        try:
            style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW)
        except Exception:
            pass
        # 不抢焦点：浏览器平台用页面失焦判定切屏，浮窗不能夺焦点
        try:
            ctypes.windll.user32.SetWindowPos(hwnd, 0xFFFFFFFE, 0, 0, 0, 0,
                                             0x0001 | 0x0002 | 0x0010 | 0x0020)
        except Exception:
            pass
        self._log(f"伪装：标题 {WIN_TITLE!r}，任务栏/Alt-Tab 隐藏，不抢焦点")

    # --- 防截屏
    @staticmethod
    def _wda(hwnd: int) -> bool:
        import ctypes

        try:
            return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
        except Exception:
            return False

    def _stealth_main(self) -> None:
        """每 5 秒重设一次反截屏 + 置顶（不抢焦点）。状态变化才打日志。"""
        import ctypes

        try:
            self._stealth_tick(ctypes.windll.user32)
        except Exception as e:
            self._log(f"[stealth] 保活异常 {type(e).__name__}: {e}")

    def _stealth_tick(self, u) -> None:
        _trace("stealth tick")
        targets = []
        try:
            if self.win:
                targets.append(int(self.win.winId()))
            if self._grid is not None and self._grid.isVisible():
                targets.append(int(self._grid.winId()))
        except Exception:
            pass
        ok = True
        for h in targets:
            if not u.IsWindow(h):  # 窗口已销毁时设 WDA 会让回调里抛异常
                continue
            try:
                ok = bool(u.SetWindowDisplayAffinity(h, WDA_EXCLUDEFROMCAPTURE)) and ok
            except Exception:
                ok = False
            try:
                u.SetWindowPos(h, 0xFFFFFFFE, 0, 0, 0, 0,
                               0x0001 | 0x0002 | 0x0010)  # TOPMOST 不改大小/不激活
            except Exception:
                pass
        if CLOAK_CONSOLE:
            try:
                import ctypes

                k32 = ctypes.windll.kernel32
                k32.GetConsoleWindow.restype = ctypes.c_void_p
                con = k32.GetConsoleWindow()
                if con and u.IsWindow(con):
                    u.SetWindowDisplayAffinity(int(con), WDA_EXCLUDEFROMCAPTURE)
            except Exception:
                pass
        if ok != self._stealth_state:
            self._stealth_state = ok
            self._log("[stealth] 反截屏保活：正常（每 5 秒校准）" if ok
                      else "[stealth] 反截屏保活：设置失败（Win10 <2004 不支持 WDA）")

    def _stealth_selfcheck(self) -> None:
        """自检：临时解除保护 → 截自己这块 → 判是否空白 → 立刻恢复保护。

        空白说明窗口本身不可见（隐藏/被遮挡），不是 WDA 的问题；有内容说明截图能拍到，
        清保护后能拍到 → 保护期间拍不到才成立。结果只做诊断，不改变行为。
        """
        if not self.win or not self.win.isVisible():
            return
        import ctypes

        hwnd = int(self.win.winId())
        g = self.win.frameGeometry()
        try:
            from PIL import ImageGrab, ImageStat
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0)  # WDA_NONE
            time.sleep(0.05)
            im = ImageGrab.grab(bbox=(g.x(), g.y(), g.x() + g.width(), g.y() + g.height()),
                                all_screens=True).convert("L")
            st = ImageStat.Stat(im)
            blank = st.stddev[0] < 2.0
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            self._log(f"[stealth] 自检：{'截图里是空白（窗口不可见/被遮挡）' if blank else '截图有内容，WDA 已恢复'}")
        except Exception as e:
            try:
                ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
            except Exception:
                pass
            self._log(f"[stealth] 自检失败 {type(e).__name__}: {e}")

    def move_by(self, dx: int, dy: int) -> None:
        """Shift+方向键移动窗口（步长 20px）。"""
        if not self.win:
            return
        p = self.win.pos()
        self.win.move(p.x() + dx, p.y() + dy)

    # --- 托盘（窗口被藏起来时的找回入口）
    def _tray(self) -> None:
        QtWidgets, QtGui, QtCore = self.QtWidgets, self.QtGui, self.QtCore
        pm = QtGui.QPixmap(32, 32)
        pm.fill(QtGui.QColor("#2a2f38"))
        p = QtGui.QPainter(pm)
        p.setPen(QtGui.QColor("#c9d1d9"))
        p.setFont(QtGui.QFont("Segoe UI", 14))
        p.drawText(pm.rect(), QtCore.Qt.AlignCenter, "S")
        p.end()
        self.tray = QtWidgets.QSystemTrayIcon(QtGui.QIcon(pm), self.win)
        self.tray.setToolTip(WIN_TITLE)
        menu = QtWidgets.QMenu()
        menu.addAction("显示/隐藏", self.toggle_visible)
        menu.addAction("快捷键", lambda: self.set_status_wrap(hotkeys.HELP_TEXT))
        menu.addAction("退出本场", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.toggle_visible()
                                    if r == QtWidgets.QSystemTrayIcon.Trigger else None)
        self.tray.show()

    # --- 点击穿透
    def toggle_click_through(self) -> bool:
        import ctypes

        if not self.win:
            return False
        hwnd = int(self.win.winId())
        style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if self.click_through:
            style &= ~WS_EX_TRANSPARENT
        else:
            style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)
        self.click_through = not self.click_through
        self._log("点击穿透 开" if self.click_through else "点击穿透 关")
        return self.click_through

    def _press(self, e):
        self._drag = e.globalPosition().toPoint() - self.win.frameGeometry().topLeft()

    def _move(self, e):
        if self._drag:
            self.win.move(e.globalPosition().toPoint() - self._drag)

    def _release(self, _):
        self._drag = None
        self._rsz = None

    # --- 鼠标直接操作：左键拖走、右下角拖大小、Ctrl+滚轮 字号、Alt+滚轮 透明度
    def eventFilter(self, obj, ev):
        """子控件（QTextBrowser 及其 viewport）上的拖动/缩放/滚轮。"""
        Q = self.QtCore
        if Q is None:
            return False
        ET = Q.QEvent.Type
        typ = ev.type()
        if typ == ET.Wheel:
            d = ev.angleDelta().y()
            if not d:
                return False
            mods = ev.modifiers()
            if mods & Q.Qt.ControlModifier:
                self.scale_step(1.1 if d > 0 else 1 / 1.1)
                return True
            if mods & Q.Qt.AltModifier:
                self.opacity_step(0.05 if d > 0 else -0.05)
                return True
            return False
        if typ == ET.MouseButtonPress and ev.button() == Q.Qt.LeftButton:
            gp = ev.globalPosition().toPoint()
            wp = self.win.mapFromGlobal(gp)
            r = self.win.rect()
            # 右下角 20px 内算缩放，其余位置拖动整窗
            if wp.x() >= r.width() - 20 and wp.y() >= r.height() - 20:
                self._rsz = (self.win.width(), self.win.height(), gp)
                self._drag = None
            else:
                self._rsz = None
                self._drag = gp - self.win.frameGeometry().topLeft()
            return True          # 吞掉，别让文本框开始选字
        if typ == ET.MouseMove:
            if not (ev.buttons() & Q.Qt.LeftButton):
                return False
            gp = ev.globalPosition().toPoint()
            if self._rsz:
                w0, h0, p0 = self._rsz
                self.win.resize(max(360, w0 + gp.x() - p0.x()),
                                max(200, h0 + gp.y() - p0.y()))
                return True
            if self._drag:
                self.win.move(gp - self._drag)
                return True
            return False
        if typ == ET.MouseButtonRelease:
            self._drag = None
            self._rsz = None
            return True
        return False

    # --- 内容
    def begin_answer(self, question: str, thumb: bytes | None = None,
                     kind: str = "text", replace: bool = False) -> None:
        if not question:
            return
        item = {"q": question, "a": "", "thumb": thumb, "kind": kind,
                "ts": time.time(), "ok": False}
        if replace and 0 <= self.idx < len(self.history):
            self.history[self.idx] = item
        else:
            self.history.append(item)
            self.idx = len(self.history) - 1
        self._list_open = False
        if not self.pinned:
            self.bridge.answer.emit("思考中…") if self.qt else self._log("思考中…")

    def set_answer(self, text: str, force: bool = False) -> None:
        if self.history and self.idx >= 0:
            self.history[self.idx]["a"] = text
        if not self.qt:
            # 无界面模式只按时间抽样打，别一个 token 一行把日志淹没
            now = time.time()
            if not force and now - self._last_render < 0.5:
                return
            self._last_render = now
            print("[屏]", text.replace("\n", " ")[:200], flush=True)
            return
        now = time.time()
        if not force and now - self._last_render < 0.12:
            return
        self._last_render = now
        # 答案到达即把窗口带到前台（不抢焦点），否则用户看不到正在生成的字
        if not self.pinned:
            self.show()
        if not self.pinned:
            self.bridge.answer.emit(text)

    def set_status(self, text: str) -> None:
        if not self.qt:
            return
        self.bridge.status.emit(text)

    def set_status_wrap(self, text: str) -> None:
        """多行内容临时占用主区域（快捷键说明）。"""
        if self.qt:
            # 交给 _render_main 统一转 HTML，别在这里预先转义
            self.bridge.answer.emit(text)
            self.bridge.status.emit("快捷键")

    # --- 识别回显 + 图形准备页
    def set_thumb(self, png: bytes) -> None:
        """截图后把原图缩略图贴进浮窗，确认没截错。任意线程可调。"""
        if 0 <= self.idx < len(self.history):
            self.history[self.idx]["thumb"] = png
        if not self.qt or not png:
            return
        self.bridge.thumb.emit(png)

    def _set_thumb_main(self, data: bytes) -> None:
        if not self.win:
            return
        if not data:
            self.thumb.clear()
            self.thumb.setVisible(False)
            self.win.adjustSize()
            return
        pix = self.QtGui.QPixmap()
        if not pix.loadFromData(data):
            return
        if pix.width() > 240 or pix.height() > 100:
            pix = pix.scaled(240, 100, self.QtCore.Qt.KeepAspectRatio,
                             self.QtCore.Qt.SmoothTransformation)
        self.thumb.setPixmap(pix)
        self.thumb.setVisible(True)
        self.win.adjustSize()

    def toggle_grid(self) -> None:
        """图形准备页：全屏网格 + 涂鸦。任意线程可调。"""
        if self.qt:
            self.bridge.grid.emit()

    def _grid_main(self) -> None:
        if not self.win:
            return
        if self._grid is None:
            from grid import Grid
            self._grid = Grid()
        vis = self._grid.toggle()
        self._log(f"图形准备页（网格+涂鸦）{'开' if vis else '关'}")

    def _set_status_main(self, text: str) -> None:
        if self.win:
            self.status.setText(text)

    def _render_main(self, text: str) -> None:
        if not self.win:
            return
        self._last_text = text
        _trace(f"render {len(text)} chars")
        t = THEMES.get(self.theme, THEMES["dark"])
        cpx = max(10, int(round(t["code_px"] * self.scale)))
        self.view.setHtml(_md_html(text, cpx, t["code_bg"], t["inline_bg"]))
        self.view.verticalScrollBar().setValue(0)
        if EXAM_GHOST and text.strip():
            self.ghost_show()

    def current_text(self) -> str:
        return self.history[self.idx]["a"] if 0 <= self.idx < len(self.history) else ""

    def nav(self, step: int) -> None:
        if not self.qt or not self.history:
            return
        self.idx = max(0, min(len(self.history) - 1, self.idx + step))
        self._list_open = False
        self.bridge.answer.emit(self.history[self.idx]["a"] or "思考中…")
        png = self.history[self.idx].get("thumb")
        if png:
            self.bridge.thumb.emit(png)
        else:
            self.bridge.thumb.emit(b"")
        self.set_status(f"第 {self.idx + 1}/{len(self.history)} 题")
        _trace(f"nav step={step:+d} idx={self.idx}/{len(self.history)}")

    def show_list(self) -> None:
        """题目列表：第 N 题 / 摘要 / 作答状态；再按一次回到当前答案。"""
        if not self.qt:
            return
        if self._list_open:
            self._list_open = False
            self.bridge.answer.emit(self.current_text() or "暂无题目")
            return
        if not self.history:
            self.set_status_wrap("题目列表\n\n（还没有题目）")
            return
        self._list_open = True
        lines = [f"题目列表（{len(self.history)}）· Ctrl+Shift+↑/↓ 切换 · Ctrl+Shift+L 返回", ""]
        for i, it in enumerate(self.history):
            mark = "▶" if i == self.idx else " "
            q = (it.get("q") or "").replace("\n", " ")
            if len(q) > 38:
                q = q[:38] + "…"
            n = len(it.get("a") or "")
            state = f"{n} 字" if n else ("作答中" if it.get("kind") == "shot" else "未答")
            lines.append(f"{mark} {i + 1}. {q}  [{state}]")
        self.set_status_wrap("\n".join(lines))

    def pin(self) -> None:
        self.pinned = not self.pinned
        self.set_status("已钉住当前答案" if self.pinned else "已取消钉住")

    # --- 热键回调转投主线程
    def post_hotkey(self, name: str, fn) -> None:
        """热键在 Win32 钩子回调里触发：就地操作 Qt 会重入窗口过程，直接让进程
        以 0xC000041D(STATUS_FATAL_USER_CALLBACK_EXCEPTION) 死掉。统一转投主线程。"""
        self._hk_fns[name] = fn
        _trace(f"hotkey:{name} (hook thread)")
        if self.qt:
            self.bridge.hotkey.emit(name)
            return
        self._hotkey_main(name)

    def _hotkey_main(self, name: str) -> None:
        fn = self._hk_fns.pop(name, None)
        if fn is None:
            return
        _trace(f"hotkey:{name} run (main thread)")
        try:
            fn()
        except Exception as e:
            self._log(f"[hotkey] {name} 出错 {type(e).__name__}: {e}")

    def scroll(self, delta: int) -> None:
        if self.win:
            bar = self.view.verticalScrollBar()
            bar.setValue(bar.value() + delta)

    def toggle_compact(self) -> None:
        """迷你窗：只要答案，屏幕占得更小。"""
        if not self.win:
            return
        self.compact = not self.compact
        self.win.resize(430 if self.compact else 560, 250 if self.compact else 400)
        self._apply_theme(self.theme)
        # 空闲卡片在迷你窗里换短版，否则一行都放不下
        txt = (self._last_text or "").strip()
        if txt in (EXAM_IDLE_HELP.strip(), EXAM_IDLE_MINI.strip()):
            self._render_main(EXAM_IDLE_MINI if self.compact else EXAM_IDLE_HELP)
        self.set_status("迷你窗，点「小」还原" if self.compact else "标准窗")

    def opacity_step(self, delta: float) -> None:
        if not self.win:
            return
        self.opacity = max(0.15, min(1.0, self.opacity + delta))
        self.win.setWindowOpacity(self.opacity)
        self.set_status(f"透明度 {self.opacity:.2f}")

    def scale_step(self, k: float) -> None:
        if not self.win:
            return
        self.scale = max(0.45, min(2.0, self.scale * k))
        # 窗口和字号一起缩放，否则只是框变大、字还是看不清
        self.win.resize(int(self.win.width() * k), int(self.win.height() * k))
        self._apply_theme(self.theme)
        self.set_status(f"缩放 {self.scale:.2f}")

    def copy(self) -> None:
        if self.qt and self.win:
            self.QtWidgets.QApplication.clipboard().setText(self.current_text())

    def toggle_visible(self) -> None:
        """任意线程可调；Qt 控件只能在主线程动，跨线程走 signal。"""
        if not self.win:
            return
        try:
            same = self.QtCore.QThread.currentThread() is self.app.thread()
        except Exception:
            same = True
        if not same:
            self.bridge.toggle.emit()
            return
        self._toggle_main()

    def _toggle_main(self) -> None:
        _trace("toggle enter")
        if self.win:
            if self.win.isVisible():
                self.hide()
            else:
                self.show()

    def show(self) -> None:
        if not self.win:
            return
        try:
            same = self.QtCore.QThread.currentThread() is self.app.thread()
        except Exception:
            same = True
        if not same:
            self.bridge.show_req.emit()
            return
        self._show_main()

    def _show_main(self) -> None:
        _trace("show enter")
        if self.win:
            old = getattr(self, "_ghost_thread", None)
            if old is not None:
                old.cancel()
            self.win.show()
            if EXAM_GHOST and MODE == "exam":
                print("[ghost] show", flush=True)
            # 只显示、不抢焦点：浏览器平台会因页面失焦判切屏
            try:
                self.win.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
            except Exception:
                pass
            try:
                import ctypes
                ctypes.windll.user32.SetWindowPos(int(self.win.winId()), 0xFFFFFFFE, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020)
            except Exception:
                pass

    def hide(self) -> None:
        if not self.win:
            return
        try:
            f = sys._getframe(1)
            _trace(f"hide enter <- {f.f_code.co_name}:{f.f_lineno}")
        except Exception:
            _trace("hide enter")
        try:
            same = self.QtCore.QThread.currentThread() is self.app.thread()
        except Exception:
            same = True
        if not same:
            self.bridge.hide_req.emit()
            return
        self._hide_main()

    def _hide_main(self) -> None:
        _trace("hide enter")
        if self.win:
            if EXAM_GHOST and MODE == "exam":
                print("[ghost] hide", flush=True)
            self.win.hide()

    def ghost_show(self) -> None:
        """幽灵窗：答案到达才出现，GHOST_HIDE_AFTER 秒后自动隐藏。只对笔试模式生效。"""
        if not EXAM_GHOST or MODE != "exam" or not self.win:
            return
        if not self.win.isVisible():
            self.show()
        self._schedule_ghost_hide()

    def _schedule_ghost_hide(self) -> None:
        if not EXAM_GHOST or not self.win:
            return
        old = getattr(self, "_ghost_thread", None)
        if old is not None:
            old.cancel()
        t = threading.Timer(max(1.0, GHOST_HIDE_AFTER), self._ghost_timeout)
        t.daemon = True
        self._ghost_thread = t
        t.start()

    def _ghost_timeout(self) -> None:
        # 线程里调 hide()：内部会 marshal 回主线程
        if EXAM_GHOST and MODE == "exam":
            print("[ghost] timer fired", flush=True)
        self.hide()

    def quit(self) -> None:
        self._save_geometry()
        self._log("退出本场")
        if self.app:
            self.app.quit()
        threading.Timer(0.4, lambda: os._exit(0)).start()

    @staticmethod
    def _log(msg: str) -> None:
        print(f"[overlay] {msg}", flush=True)

    def run(self) -> None:
        if self.qt:
            _trace("exec enter")
            self.app.exec()
            _trace("exec returned")

# ---------------------------------------------------------------- 主流程
def _ensure_audio(level: float = 0.3) -> None:
    """默认输出静音时 loopback 抓到的全是 0，而且不报错；启动时只救「静音/音量近乎 0」，
    正常音量不动（戴着耳机时别突然把声音放大）。"""
    if not AUDIO_AUTOFIX:
        return
    try:
        import ctypes

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        from pycaw.utils import AudioUtilities

        sp = AudioUtilities.GetSpeakers()
        iface = sp._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))
        mute, cur = bool(vol.GetMute()), float(vol.GetMasterVolumeLevelScalar())
        if mute:
            vol.SetMute(0, None)
            print(f"[audio] {sp.FriendlyName} 原本静音，已解除", flush=True)
        if cur < 0.02:
            vol.SetMasterVolumeLevelScalar(level, None)
            print(f"[audio] {sp.FriendlyName} 音量 {cur:.2f} 太低，已调到 {level:.2f}", flush=True)
        else:
            print(f"[audio] {sp.FriendlyName} mute={int(mute)} 音量={cur:.2f}", flush=True)
        # pycaw 的 COM 对象在解释器退出时析构会报 access violation（无害但吓人），提前在这里放掉
        del vol, iface, sp
        import gc

        gc.collect()
    except Exception as e:
        print(f"[audio] 音量自检跳过（{type(e).__name__}: {e}）", flush=True)


def _shot_prompt() -> str:
    if MODE == "exam":
        return (
            "你在帮用户做在线笔试。下面是用户当前的屏幕截图。\n"
            f"编程语言：{EXAM_LANG}；代码模式：{EXAM_STYLE}。\n"
            "规则：\n"
            "0) 第一行必须先输出题型标记，格式严格为："
            "【题型】编程题 / 【题型】选择题 / 【题型】判断题 / 【题型】填空题 / "
            "【题型】技术问答 / 【题型】图形推理 / 【题型】未识别。只写一个。\n"
            "1) 先判断截图里有没有可作答的题目（题号/问号/请实现/手撕/选项/输入输出示例都算）。\n"
            "2) 判断题型，按下面的方式作答。"
            "**凡是直接可抄的答案（选项/对错/填空内容/结论/代码）一律以「【答案】」开头；"
            "思路、依据、复杂度等解释一律以「【解析】」开头。两者必须分开成行，不许混在一句里。**\n"
            "   - 编程题：先看清题目自带的代码模板和函数签名（class Solution、参数名、ListNode 等），"
            "沿用原模板和原签名只补函数体，保证复制进去就能提交；语言以截图模板为准。"
            "格式：「【解析】思路 2-3 行」→「【答案】」+ 完整代码块 →「【解析】时间复杂度」。"
            "代码块里必须有完整的 class/函数定义。\n"
            "   - 技术问答题：「【答案】」一句话结论 +「【解析】」3-5 个要点，术语保留英文。\n"
            "   - 选择题：「【答案】X」+「【解析】」一句不超过 30 字的依据（多选按字母顺序），不要分析其它选项。\n"
            "   - 判断题：「【答案】对」或「【答案】错」+「【解析】」一句不超过 30 字的依据。\n"
            "   - 填空题：「【答案】」填好的内容（按题目模板再写一遍）+「【解析】」关键依据。\n"
            "   - 行测/图形推理：「【答案】选项」+「【解析】」图形规律（数量/位置/样式/叠加/对称/旋转）。\n"
            "   - 其他：「【答案】」最短可用答案 +「【解析】」必要说明。\n"
            "3) 题干没截全就先指出缺了什么，再给能确定的部分，不要硬猜。\n"
            "4) 没有可作答题目时，第一行写「【题型】未识别」，第二行写「未识别到题目（看到的是："
            "<桌面/视频会议/登录页/简历/PPT/聊天气泡/文件管理器/其他>），请重新框选题目区域」。\n"
            "5) 代码用 Markdown 代码块，先保证能跑。"
        )
    return (
        "你在帮用户看面试时的屏幕截图（通常是手撕代码题、系统设计图、PPT 或题目页面）。\n"
        "有题目就结合当前面试上下文直接给思路和代码，沿用截图里的函数签名和语言；"
        "没有可作答内容就只回一句「未识别到题目」。"
    )


_KIND_RE = re.compile(r"【题型】\s*(编程题|选择题|判断题|填空题|技术问答|图形推理|未识别)")
_CODE_SIG_RE = re.compile(
    r"(class\s+[A-Za-z_]\w*"
    r"|def\s+[A-Za-z_]\w*\s*\("
    r"|func\s+[A-Za-z_]\w*\s*\("
    r"|function\s+[A-Za-z_]\w*\s*\("
    r"|(?:public|private|protected|static)[^\n(]{0,40}\s+[A-Za-z_]\w*\s*\([^)]*\)\s*\{?)"
)
_SHOT_RETRY_HINT = (
    "\n\n重要：上一版没有给出完整的函数签名或代码块。"
    "请严格照抄截图里的代码模板（class Solution、函数名、参数名、返回类型），只补函数体，"
    "输出一个完整、可直接复制的代码块，不要省略签名。"
)


def _exam_kind(text: str) -> str:
    m = _KIND_RE.search(text)
    return m.group(1) if m else ""


def _exam_tidy(text: str) -> str:
    """选择题/判断题压到最短：题型标记 + 答案首行 + 最多一句依据。"""
    kind = _exam_kind(text)
    if kind not in ("选择题", "判断题"):
        return text
    m = _KIND_RE.search(text)
    body = text[m.end():].lstrip(" \n:：-") if m else text
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    keep: list[str] = []
    for ln in lines:
        keep.append(ln[:120])
        if len(keep) >= 2 or sum(len(x) for x in keep) >= 90:
            break
    return f"【题型】{kind}\n" + "\n".join(keep)


def _code_ok(text: str) -> bool:
    return bool(_CODE_SIG_RE.search(text))


def _is_coding(text: str) -> bool:
    kind = _exam_kind(text)
    if kind == "编程题":
        return True
    return kind in ("", "技术问答") and ("时间复杂度" in text or "```" in text)


def _looks_unrecognized(text: str) -> bool:
    t = text.strip()
    if not t:
        return True
    if _exam_kind(t) == "未识别":
        return True
    m = _KIND_RE.search(t)
    body = t[m.end():].lstrip(" \n:：-").lower() if m else t.lower()
    return body.startswith(("未识别", "没有识别", "识别不"))


def _vision_once(brain, png: bytes, prompt: str, on_delta, cancel=None) -> str:
    text = brain.answer_image(png, prompt, on_delta, cancel=cancel)
    return _exam_tidy(text) if MODE == "exam" else text


def _exam_vision(brain, png: bytes, prompt: str, on_delta, cancel=None, on_retry=None) -> str:
    """笔试截图作答：题型分流 + 编程题缺签名时带模板提示重试一次。"""
    text = _vision_once(brain, png, prompt, on_delta, cancel)
    if MODE != "exam" or _looks_unrecognized(text):
        return text
    if not (_is_coding(text) and not _code_ok(text)):
        return text
    if cancel is not None and cancel.is_set():
        return text
    print("[shot] 缺函数签名，带模板提示重试一次", flush=True)
    if on_retry:
        on_retry()
    return _vision_once(brain, png, prompt + _SHOT_RETRY_HINT, on_delta, cancel)


def main() -> None:
    _enable_faulthandler()
    _install_excepthooks()
    _trace(f"=== start mode={MODE} py={sys.version.split()[0]} pid={os.getpid()}")
    if CLOAK_CONSOLE:
        print(f"[cloak] 控制台反截屏 = {_cloak_console()}", flush=True)
    if MODE == "exam" and "--no-ui" not in sys.argv:
        _mode = "hide" if CONSOLE_HIDE else ("min" if CONSOLE_MIN else "show")
        state = _console_setup(_mode, CONSOLE_TITLE)
        print(f"[console] 标题={CONSOLE_TITLE!r} 状态={state}（Ctrl+Shift+Q 两下退出；日志见 run.log）",
              flush=True)
    if MODE == "exam" and "--no-ui" not in sys.argv and _show_running():
        print("[overlay] 已有实例在跑，已经把它叫出来了（本次启动直接退出）", flush=True)
        return
    ui = Overlay()
    _trace("overlay ready")
    _ShowServer(ui).start()
    if MODE == "exam" and (EXAM_GHOST or EXAM_SAFE) and ui.win:
        ui.hide()  # 一开始就不让窗口出现在共享画面里
    raw_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=400)
    seg_q: "queue.Queue[tuple[str, np.ndarray]]" = queue.Queue()

    # 笔试模式是「截图 → 视觉模型 → 答案」，不听课，所以不采集、不跑 ASR
    audio_on = MODE != "exam"
    cap = None
    if audio_on:
        _ensure_audio()
        cap = LoopbackCapture(raw_q)
        cap.start()
        VadSegmenter(raw_q, seg_q, partial_step=PARTIAL_STEP, hang=HANG, spec_hang=SPEC_HANG).start()

    from profile import Profile

    profile = Profile()
    print(profile.summary(), flush=True)
    for err in profile.errors:
        print(f"[profile] {err}", flush=True)
    brain = Brain(os.getenv("ROLE", "后端工程师"),
                  profile.resume_text(os.getenv("RESUME", "")),
                  context=profile.context_block(),
                  addon=profile.prompt_addon(MODE))
    print(f"[llm] 档位 {LLM_PROFILE}｜速答 {'开' if QUICK_ANSWER else '关'}｜"
          f"翻译对照 {'开' if TRANSLATE else '关'}｜资料 {len(profile.knowledge)} 份", flush=True)
    last_text: list[str] = [""]
    ask_lock = threading.Lock()
    ask_cancel = threading.Event()

    # ---- 保活：relay 冷下来首字 3.7–9s，热着 0.4–1.1s。
    # 放在 Asr() 之前：加载模型那十几秒顺便把 relay 热好，第一题就不用吃冷启动。
    if os.getenv("LLM_WARM", "1") not in ("0", "false", "False"):
        def _keep_warm() -> None:
            try:
                brain.warm()
            except Exception:
                pass
            try:
                brain.warm_vision()
            except Exception:
                pass
            while True:
                time.sleep(10)
                if ask_lock.locked():
                    continue
                if brain.last_used and time.time() - brain.last_used > 50:
                    try:
                        brain.warm(quiet=True)
                        brain.warm_vision(quiet=True)
                    except Exception:
                        pass

        threading.Thread(target=_keep_warm, daemon=True).start()

    asr = Asr() if audio_on else None

    from bank import QuestionBank
    from tts import Speaker

    bank = QuestionBank()
    speaker = Speaker(enabled=TTS_ON)

    # ---- 手机联动
    pad = None

    def on_cmd(cmd: str) -> None:
        print(f"[mobile] 指令 {cmd}", flush=True)
        if cmd == "show":
            ui.show()
        elif cmd == "hide":
            ui.hide()
        elif cmd in ("shot", "shot_window", "shot_long"):
            shotter.trigger({"shot": "full", "shot_window": "window", "shot_long": "long"}[cmd])
        elif cmd == "prev":
            ui.nav(-1)
        elif cmd == "next":
            ui.nav(1)
        elif cmd == "opacity_up":
            ui.opacity_step(0.05)
        elif cmd == "opacity_down":
            ui.opacity_step(-0.05)
        elif cmd == "scale_up":
            ui.scale_step(1.08)
        elif cmd == "scale_down":
            ui.scale_step(1 / 1.08)
        elif cmd == "scroll_up":
            ui.scroll(-120)
        elif cmd == "scroll_down":
            ui.scroll(120)
        elif cmd == "pin":
            ui.pin()
        elif cmd == "cancel":
            ask_cancel.set()
            shotter.cancel()
            speaker.stop()
        elif cmd == "exit":
            ui.quit()

    if MOBILE_ON:
        from mobile import MobilePad

        pad = MobilePad(on_cmd, port=MOBILE_PORT)
        pad.start()

    # ---- 截图 → 视觉模型
    last_png: list[bytes] = [b""]

    def on_shot(png: bytes, cancel_evt: threading.Event, replace: bool = False) -> None:
        last_png[0] = png
        ui.begin_answer("（截图）", thumb=png, kind="shot", replace=replace)
        ui.set_status("识别截图中…")
        ui.set_thumb(png)  # 回显原图缩略图，确认没截错
        buf: list[str] = []

        def on_delta(piece: str) -> None:
            buf.append(piece)
            ui.set_answer("".join(buf))

        # 题目区域智能放大（长边 1600 内尽量放大到可读字号），转 JPEG 减小 payload
        png = _shot_mod.prepare(png)
        t0 = time.time()
        try:
            text = _exam_vision(brain, png, _shot_prompt(), on_delta, cancel_evt,
                                on_retry=buf.clear)
        except Exception as e:
            print(f"[shot] {type(e).__name__}: {e}", flush=True)
            ui.set_answer(f"[截图识别失败] {type(e).__name__}: {e}", force=True)
            return
        print(f"[shot] 识别 {time.time()-t0:.2f}s", flush=True)
        if cancel_evt.is_set():
            ui.set_answer("".join(buf) + "\n\n（已取消，答案保留到这里）", force=True)
            return
        # 视觉模型没出字就回「未识别到题目」——不覆盖上一题的可用答案
        if _looks_unrecognized(text):
            ui.set_answer(text.strip() or "未识别到题目，请重新框选题目区域", force=True)
            ui.set_status("未识别到题目")
            return
        ui.set_answer(text, force=True)
        ui.set_status("截图答案")
        if 0 <= ui.idx < len(ui.history):
            ui.history[ui.idx]["ok"] = True
        print(f"[shot] 答案 {len(text)} 字", flush=True)
        if pad:
            pad.update(question="（截图）", answer=text)
        if TTS_ON:
            speaker.speak(text)

    from shot import Screenshotter
    import shot as _shot_mod

    shotter = Screenshotter(
        on_shot,
        ui.set_status,
        before_grab=ui.grab_hide if SHOT_HIDE_UI else None,
        after_grab=ui.grab_show if SHOT_HIDE_UI else None,
    )

    if MODE == "exam" and EXAM_SAFE:
        ui.hide()
        if not ui.click_through:
            ui.toggle_click_through()
        # 隐藏状态下再显示也走 show()：不抢焦点
        print("[exam] 安全模式：窗口默认隐藏 + 点击穿透，按 F8 显示（不抢焦点）", flush=True)
    elif MODE == "exam" and ui.win:
        g = ui.win.frameGeometry()
        print(f"[exam] 答案窗在屏幕右上角（{g.width()}x{g.height()} @ {g.x()},{g.y()}，标题 Settings）", flush=True)
        print("[exam] 用法：Shift+双击 截图 → 窗口流出答案；F8 显隐；F9 点击穿透；Ctrl+Shift+Q 两下退出", flush=True)
        if EXAM_GHOST:
            ui.hide()
            print(f"[exam] 幽灵窗：默认隐藏，答案到达才显示，{GHOST_HIDE_AFTER:.0f} 秒后自动隐藏（F8 可随时叫出）", flush=True)
        elif EXAM_IDLE:
            ui.set_status_wrap(EXAM_IDLE_HELP)
            ui.set_status("Shift+双击 截屏出答案 ｜ F8 显隐 ｜ 退出 Ctrl+Shift+Q 连按两次")
            print("[exam] 空闲卡片：窗口常驻（共享里不可见），未截图时显示快捷键", flush=True)

    # ---- 动作捕捉（可选）：扶眼镜 / 眨眼两下 触发整屏截图
    if GESTURE_ON:
        from gesture import GestureWatcher

        gw = GestureWatcher(
            lambda kind: shotter.trigger("full"),
            on_progress=lambda p, t: ui.set_status(t) if t else ui.set_status("听面试官说话…"),
        )
        gw.start()

    hidden_once: list[bool] = [False]

    def _maybe_hide_desktop() -> None:
        """手机联动 + MOBILE_HIDE：第一题开始后 3 秒把本机窗口藏起来（答案在手机上）。"""
        if not (MOBILE_HIDE and pad) or hidden_once[0]:
            return
        hidden_once[0] = True

        def run() -> None:
            for i in (3, 2, 1):
                ui.set_status(f"{i} 秒后隐藏本机窗口（手机看答案）")
                time.sleep(1)
            ui.hide()
            print("[mobile] 本机窗口已隐藏，答案看手机", flush=True)
        threading.Thread(target=run, daemon=True).start()

    def _use_bank(text: str) -> bool:
        hit = bank.match(text)
        if not hit:
            return False
        print(f"[题库命中] {hit[0]}", flush=True)
        ui.begin_answer(text)
        ui.set_answer(hit[1], force=True)
        ui.set_status("题库命中 · 原样使用")
        if pad:
            pad.update(question=text, answer=hit[1])
        if TTS_ON:
            speaker.speak(hit[1])
        return True

    def ask(text: str, t0: float | None = None, early: bool = False) -> None:
        _maybe_hide_desktop()
        ui.begin_answer(text)
        ui.set_status("思考中…")
        if pad:
            pad.update(question=text, answer="")
        ask_cancel.clear()
        buf: list[str] = []
        first: list[float] = []
        t_reason: list[float] = []

        # ⚡速答：和完整回答并行跑，抢在首字前先给一句结论；完整回答的第一块一到就覆盖它
        if QUICK_ANSWER:
            def _quick() -> None:
                qa = brain.quick(text)
                if qa and not ask_cancel.is_set() and not first:
                    ui.set_answer("⚡ 速答：" + qa + "\n\n（完整回答生成中…）", force=True)
                    t = f" {time.time()-t0:.2f}s" if t0 else ""
                    print(f"[速答{t}] {qa}", flush=True)

            threading.Thread(target=_quick, daemon=True).start()

        def on_reason(_piece: str) -> None:
            if not t_reason:
                t_reason.append(time.time())
                ui.set_status("思考中…（模型在推理）")

        def on_delta(piece: str) -> None:
            if not first:
                first.append(time.time())
                ui.set_status("生成中…")
            buf.append(piece)
            ui.set_answer("".join(buf))

        try:
            text_out = brain.answer(text, on_delta, on_reason=on_reason, cancel=ask_cancel)
        except Exception as e:
            ui.set_answer(f"[LLM 失败] {type(e).__name__}: {e}", force=True)
            print(f"[llm] 失败: {type(e).__name__}: {e}", flush=True)
            return
        if ask_cancel.is_set():
            ui.set_answer("".join(buf) + "\n\n（已取消，答案保留到这里）", force=True)
            return
        ui.set_answer(text_out, force=True)
        ui.set_status("答案就绪 · Ctrl+Shift+C 复制")
        if pad:
            pad.update(answer=text_out)
        if t0:
            rt = f"，思考首字 {t_reason[0]-t0:.2f}s" if t_reason else ""
            ft = f"，正文首字 {first[0]-t0:.2f}s" if first else ""
            print(f"[{'早触发' if early else '作答'} 总 {time.time()-t0:.2f}s{rt}{ft}]", flush=True)
        if TTS_ON:
            speaker.speak(text_out)

    def start_ask(text: str, t0: float = 0.0, early: bool = False, wait: bool = False) -> None:
        def run():
            if wait:
                ask_lock.acquire()
            elif not ask_lock.acquire(blocking=False):
                print("[llm] 上一句还在生成，跳过这句", flush=True)
                return
            try:
                ask(text, t0, early)
            finally:
                ask_lock.release()

        threading.Thread(target=run, daemon=True).start()

    def dom_read() -> str:
        """从笔试页面读题干（CDP 优先，UIA 兜底）。只读，不截图、不注入。"""
        try:
            import dom as _dom
        except Exception as e:
            print(f"[dom] 模块不可用 {type(e).__name__}: {e}", flush=True)
            return ""
        q, src = _dom.read_question_ex()
        if q:
            print(f"[dom] {src or '?'} 读到 {len(q)} 字：{q[:50]}", flush=True)
        return q

    def dom_ask() -> None:
        q = dom_read()
        if not q:
            ui.set_status("没读到题目：先用 dom.open_debug_browser() 打开带调试端口的浏览器")
            print("[dom] 没读到题目（CDP 未连上且可访问性树没有正文）", flush=True)
            return
        ui.set_status("DOM 读题成功")
        start_ask(q, time.time())

    def follow_up() -> None:
        """追问预判：基于当前题和答案，列出面试官可能的追问。"""
        print("[follow] 触发", flush=True)
        if not ui.history:
            ui.set_status("还没有题目")
            print("[follow] 历史为空，跳过", flush=True)
            return
        item = ui.history[ui.idx]
        q, a = item.get("q", ""), item.get("a", "")
        ui.set_status("分析可能的追问…")
        idx = ui.idx

        def run() -> None:
            extra = brain.supplement(q, a)
            if not extra:
                ui.set_status("追问分析失败")
                print("[follow] 模型没返回内容（检查 relay / key）", flush=True)
                return
            cur = ui.history[idx]["a"] if 0 <= idx < len(ui.history) else a
            ui.set_answer(cur + "\n\n---\n**可能追问**\n" + extra, force=True)
            ui.set_status("追问已追加 · Ctrl+Shift+C 复制")
            print(f"[follow] 追问 {len(extra)} 字", flush=True)

        threading.Thread(target=run, daemon=True).start()

    def worker() -> None:
        early_text: list[str] = [""]
        while True:
            kind, pcm = seg_q.get()
            t0 = time.time()
            text = asr.transcribe(pcm)
            if not text:
                continue
            if kind != "final":
                # 半句/预断句命中疑问词就先发出去，模型思考的那 2s 用来覆盖说完的最后几个字
                if not EARLY_ASK or early_text[0]:
                    continue
                if _use_bank(text):
                    early_text[0] = text
                    continue
                if len(text) >= 6 and is_question(text):
                    early_text[0] = text
                    tag = "中间态" if kind == "partial" else "预断句"
                    print(f"\n[{tag} {time.time()-t0:.2f}s → 提前发问] {text}", flush=True)
                    start_ask(text, t0, early=True)
                continue
            last_text[0] = text
            print(f"\n[听到 {time.time()-t0:.2f}s] {text}", flush=True)
            if pad:
                pad.update(status="已识别问题")
            if early_text[0]:
                hit = early_text[0] in text or text.startswith(early_text[0][:8])
                early_text[0] = ""
                if hit:
                    print("[早触发命中，沿用已出的答案]", flush=True)
                    continue
                print("[早触发文本与整句差异大，重新作答]", flush=True)
                if _use_bank(text):
                    continue
                if is_question(text):
                    start_ask(text, t0, wait=True)
                continue
            if _use_bank(text):
                continue
            if is_question(text):
                start_ask(text, t0)

    if audio_on:
        threading.Thread(target=worker, daemon=True).start()

    # ---- 全局热键
    def force_submit() -> None:
        if MODE == "exam":
            # 笔试：复用上一张截图重跑识别，避免重复截屏（对应官方「重新截图可再试一次」）
            resend()
            return
        if last_text[0]:
            print(f"[hotkey] 强制提交：{last_text[0]}", flush=True)
            start_ask(last_text[0])
        elif ui.current_text():
            start_ask(ui.history[ui.idx]["q"] if ui.history else "")

    def resend() -> None:
        """笔试：重新识别当前这张截图（不重新截屏）。"""
        if not last_png[0]:
            print("[shot] 还没有截图，先按 Shift+双击截一张", flush=True)
            ui.set_status("还没有截图")
            return
        ev = threading.Event()
        threading.Thread(target=on_shot, args=(last_png[0], ev, True),
                         daemon=True).start()
        print("[shot] 重新识别当前截图", flush=True)

    def retake() -> None:
        """重答：笔试=重新截一张；面试=重答上一题。"""
        if MODE == "exam":
            shotter.trigger("full")
        elif ui.current_text():
            start_ask(ui.history[ui.idx]["q"] if ui.history else "")

    def cancel_all() -> None:
        ask_cancel.set()
        shotter.cancel()
        speaker.stop()
        print("[hotkey] 已取消当前截图/作答", flush=True)

    cbs = {
        "toggle": ui.toggle_visible,
        "exit": ui.quit,
        "prev": lambda: ui.nav(-1),
        "next": lambda: ui.nav(1),
        "pin": ui.pin,
        "force": force_submit,
        "cancel": cancel_all,
        "opacity_up": lambda: ui.opacity_step(0.05),
        "opacity_down": lambda: ui.opacity_step(-0.05),
        "scale_up": lambda: ui.scale_step(1.08),
        "scale_down": lambda: ui.scale_step(1 / 1.08),
        "scroll_up": lambda: ui.scroll(-120),
        "scroll_down": lambda: ui.scroll(120),
        "copy": ui.copy,
        "help": lambda: ui.set_status_wrap(hotkeys.HELP_TEXT),
        "clear": lambda: ui.set_answer("", force=True),
        "click_through": ui.toggle_click_through if ui.win else None,
        "theme": ui.cycle_theme if ui.win else None,
        "compact": ui.toggle_compact if ui.win else None,
        "retake": retake,
        "shot_full": (lambda: shotter.trigger("full")) if MODE == "exam" else None,
        "shot_window": (lambda: shotter.trigger("window")) if MODE == "exam" else None,
        "shot_long": (lambda: shotter.trigger("long")) if MODE == "exam" else None,
        "region": (lambda: ui.request_region(lambda rect: shotter.trigger("region", rect=rect)))
        if ui.win else None,
        "grid": (lambda: ui.toggle_grid()) if ui.win else None,
        "list": ui.show_list,
        "dom": dom_ask if DOM_ON else None,
        "follow": follow_up,
        "move_up": lambda: ui.move_by(0, -20),
        "move_down": lambda: ui.move_by(0, 20),
        "move_left": lambda: ui.move_by(-20, 0),
        "move_right": lambda: ui.move_by(20, 0),
    }
    try:
        hotkeys.install(cbs, post=ui.post_hotkey)
        if SHOT_MOUSE:
            hotkeys.MouseHooks(
                lambda kind, x, y: shotter.trigger(kind, x, y),
                clicks=SHOT_CLICKS,
                button=SHOT_BUTTON,
                interval=SHOT_INTERVAL,
                dist=SHOT_DIST,
            ).start()
    except Exception as e:
        print(f"[hotkey] 未启用: {type(e).__name__}: {e}", flush=True)

    if MODE == "exam" and DOM_ON and DOM_AUTO:
        def _dom_loop() -> None:
            try:
                import dom as _dom
            except Exception as e:
                print(f"[dom] 自动读题不可用 {type(e).__name__}: {e}", flush=True)
                return
            last = ""
            while True:
                time.sleep(2.0)
                if ask_lock.locked():
                    continue
                q, src = _dom.read_question_ex()
                if not q or q == last or len(q) < 20:
                    continue
                last = q
                if _dom.looks_like_question(q):
                    print(f"[dom] 题目变化（{src}）→ 自动作答", flush=True)
                    start_ask(q, time.time())

        threading.Thread(target=_dom_loop, daemon=True).start()
        print("[dom] 自动读题=开（2 秒轮询，题干变化才作答）", flush=True)

    if audio_on:
        print(f"[capture] 采集中: {cap.device or '默认输出设备'}", flush=True)
        print(f"[asr] {asr.mode}", flush=True)
    if not OPENAI_API_KEY:
        print("[llm] 未配置 OPENAI_API_KEY：只做识别不出答案，请复制 .env.example 为 .env 后填写", flush=True)
    else:
        eff = f" effort={LLM_REASONING_EFFORT}" if LLM_REASONING_EFFORT else ""
        print(f"[llm] {LLM_MODEL}{eff} @ {OPENAI_BASE_URL}｜视觉 {VISION_MODEL}", flush=True)
    if audio_on:
        print(f"[vad] 早触发={'开' if EARLY_ASK else '关'} 中间态间隔={PARTIAL_STEP}s", flush=True)
    print(f"[mode] {MODE}｜伪装标题 {WIN_TITLE!r}｜语音播报 {'开' if TTS_ON else '关'}", flush=True)
    if MODE == "exam":
        print("[exam] 截图作答：Shift+双击 整屏 / Alt+双击 窗口 / Ctrl+Shift+S 框选 / Shift+Alt+双击 长截图", flush=True)
        print(f"[exam] 语言={EXAM_LANG}｜代码模式={EXAM_STYLE}｜取消 Ctrl+Shift+X", flush=True)
        if DOM_ON:
            print(f"[dom] 读题=开（Ctrl+Shift+D）｜CDP {os.getenv('DOM_CDP', 'http://127.0.0.1:9223')}"
                  f"｜自动 {('开' if DOM_AUTO else '关')}", flush=True)
    if GESTURE_ON:
        print(f"[gesture] 动作捕捉={'开' if not getattr(gw, 'error', None) else '失败'}"
              f"｜模式 {os.getenv('GESTURE_MODE', 'glasses')}", flush=True)
    print(bank.summary(), flush=True)
    if TTS_ON and speaker.error:
        print(f"[tts] 初始化失败: {speaker.error}", flush=True)
    ui.set_status("Shift+双击 截屏出答案 · Ctrl+Shift+S 框选" if MODE == "exam" else "听面试官说话…")
    _trace("before ui.run")
    if not ui.win:
        # 无界面时保持进程存活，把识别结果打到控制台
        while True:
            time.sleep(0.5)
    ui.run()


if __name__ == "__main__":
    main()
