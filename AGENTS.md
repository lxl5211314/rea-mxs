# AGENTS.md — msx-clone（E:\aaa_msx）

自研面试/笔试辅助工具：通过系统音频 loopback 采集会议声音 → VAD → 本地 ASR →
判定问题 → 题库命中或 LLM 作答 → 置顶透明浮窗/手机页/语音播报。
商业客户端「面试侠」逆向只做参考，不复制其服务端逻辑。

## Tech Stack

- Python 3.13.2（解释器 `E:\python3.10.4\python.exe`，pip 镜像清华）
- 采集：`soundcard` 0.4.6（WASAPI loopback）、`numpy`
- ASR：`faster-whisper` 1.2.1 + `ctranslate2` 4.8.5（base 模型 @ CUDA，RTX 4050 6G）
- 视觉：`mediapipe` >=1.2（Tasks API，无 `mp.solutions`）+ `opencv-contrib-python`（CAP_DSHOW）
- UI：`PySide6` 6.12.0（置顶透明窗 + `SetWindowDisplayAffinity` WDA_EXCLUDEFROMCAPTURE）
- 热键：`keyboard`；截图：`Pillow` 12.2.0；TTS：SAPI（`tts.py`）；手机联动：自带 HTTP + `qrcode`
- LLM：OpenAI 兼容客户端走本机「智能交付」relay `http://127.0.0.1:19300/v1`（key `local-yonyou-relay`），**不必用本地 LLM**

## Project Structure

- `clone/` — 自研代码（主战场）。`mvp.py` 是主程序；其余为模块：`profile.py`(岗位/简历/知识库/提示词) `shot.py`(截图) `bank.py`(题库) `tts.py`(语音) `mobile.py`(手机页) `hotkeys.py`(热键) `gesture.py`(动作捕捉) `selftest.py`(自检) `live_test.py`(端到端)
- `clone/资料/` — 用户资料目录（`简历.*` 1 份、`知识库/*` ≤2 份、`提示词_面试.txt`/`提示词_笔试.txt`），本地解析，不上传；`profile.py` 读它
- `clone/start.bat`(面试) / `start-exam.bat`(笔试，首次启动进准备页；`start-exam.bat setup` 重设语言/代码模式) — 只有这两个 Windows 入口（纯 ASCII + CRLF）；自检用 `python selftest.py deps|e2e|llm`，无界面用 `python mvp.py --no-ui`
- 根目录 `E:\aaa_msx\` 下同名 2 个 bat 只是转发入口（`cd /d "%~dp0clone"` + `call`），真正逻辑只在 `clone/` 那份，改逻辑不要动根目录
- `docs/` — 报告与日志：`交接文档.md`、`开发日志.md`、`面试侠逆向报告.md`
- `reverse/` — 逆向素材（只读参考，不改）：`bundle_pretty.js` 为前端源码行号索引基准
- `models/` — 已离线模型：`faster-whisper-{tiny,base}`、`face_landmarker.task`、`hand_landmarker.task`

## Development Commands

在 `E:\aaa_msx\clone` 下（PowerShell 先 `$env:PYTHONIOENCODING="utf-8"`）：

- 语法检查：`python -m py_compile mvp.py selftest.py live_test.py`
- 分层自检：`python selftest.py deps|capture|asr|e2e|llm`
- 端到端实机：`python live_test.py <wav>`（后台起 mvp --no-ui，9s 后播 wav，输出写 `live.log`）
- 主程序 GUI：`python mvp.py`（约 20s 就绪；进程需 `Stop-Process` 结束）
- 动作捕捉单独自测：`python gesture_test.py glasses|blink <秒>`
- 模块离线自检：`python features_test.py`（题库/视觉/手机，输出写 `features.log`）

## Critical Conventions

- **配置只走 `.env`**（同目录，不进 git）。`_load_env()` 用 `setdefault`，所以 **bat 里 `set MODE=...` 优先于 `.env`**（`start.bat`=interview、`start-exam.bat`=exam）。`MODELS_DIR` 必须在 `_load_env()` 之后读取，否则 `MSX_MODELS_DIR` 不生效。
- **面试/笔试是两条链路，别混**：`MODE=exam` 时 `audio_on=False`，不初始化采集/VAD/ASR/worker，只有截图→视觉→答案；`MODE=interview` 才有 loopback 与早触发。笔试就绪约 3s（无 `[capture]`/`[asr]` 日志才是对的）。
- **手机联动默认 `MOBILE=0`**（不打印二维码、不开 8765 端口）；`MOBILE_HIDE` 只是第一题后藏窗口，不控制端口。
- **LLM 流式**：默认 `LLM_EXTRA_JSON={"thinking":{"type":"disabled"}}` 关掉推理（否则正文首字 3–5s）；`LLM_WARM=1` 保活线程（冷态 3.8s vs 热态 0.4s，10 倍差距）。
- **回答档位 `LLM_PROFILE`**：`speed`=灵动（默认，关思考，首字最快）/ `natural`=睿智（未显式配 EFFORT/EXTRA 时用 `reasoning_effort=high`，更像口语气但慢）。
- **速答 `QUICK_ANSWER=1`**：`Brain.quick()` 非流式一句话（≤40 字）先上屏，完整回答首块到达即覆盖；实测只让完整回答首字 +0.15s，默认开。
- **资料 `profile.py`**：`clone\资料`（或 `MSX_PROFILE_DIR`）里的简历/知识库/提示词会被注入 `Brain.system`；单文件 ≤3MB、简历 1 份、知识库 ≤2 份、单条提示词 ≤2000 字；`.doc` 不支持（提示另存 docx）。内容只本地解析。
- **翻译对照 `TRANSLATE=1`**：英/日/韩问题先给一行「【中文对照】」，再正常作答；中文问题无额外开销。
- **样式预设 `THEME`**：`dark`(极暗低调) / `blue`(护眼蓝灰) / `large`(大字清晰)，`mvp.py` 的 `THEMES` 表统一管背景/字色/字号/代码块；`Ctrl+Alt+Y` 运行时循环，`_md_html(text, code_px, code_bg, inline_bg)` 必须带主题参数，别再写死颜色。
- **ASR 必须本地**：relay 的 `/v1/audio/transcriptions` 返回 404，无云端转写。
- **不用本地 LLM**：视觉模型也用同一个 relay（`deepseek-v4.1-flash` + 关思考），首字 1.4s；`deepseek-v4.1-flash` 默认模式回空串，必须带关思考。
- **不主动 git commit / push**（仓库当前不是 git repo）。
- **每次迭代/升级/改功能后，必须同步更新对应文档**：`docs/开发日志.md`（当日做了什么、实测数字、踩的坑）、`clone/README.md`（功能表/配置/差距）、根 `README.md`（进度表）、`.env.example`（新环境变量）；新增模块或目录时更新本文件 `AGENTS.md` 的结构与约定。文档没更新视为改动未完成。
- **Windows 控制台 GBK**：直接 print 中文会乱码/丢字。用 `$env:PYTHONIOENCODING="utf-8"`，或让脚本写 utf-8 文件再用 read 看。PowerShell 不支持 bash here-doc；多行 Python 写临时 `.py` 再执行。
- **bat 启动脚本必须 ASCII + CRLF**（只有 `clone/start.bat`、`clone/start-exam.bat`）：cmd.exe 按 GBK 解析批处理文件，UTF-8 中文注释会让整行错位（报 `'保活' 不是内部或外部命令`）；LF-only 换行会让 `rem`/括号块解析失败。中文说明只写进 README/文档。
- **入口只保留两个**：`start.bat`(面试) / `start-exam.bat`(笔试)。不要新增 `check.bat`、`exam-setup.bat`、`start-no-ui.bat` 这类入口；自检写进 `selftest.py`，无界面用 `--no-ui`，准备页由 `start-exam.bat` 自己按 `EXAM_LANG` 是否存在触发（`findstr /b /c:"EXAM_LANG=" .env`）。
- **bat 里脚本路径**：`cd /d "%~dp0"` + `set PYTHONIOENCODING=utf-8` + `set PYTHONUTF8=1` + `where python` 失败回退 `E:\python3.10.4\python.exe`；`.env` 缺失时从 `.env.example` 复制。
- **COM 线程模型**：`soundcard` 顶层导入会设 MTA，`comtypes`/`pycaw` 想要 STA → 冲突。采集线程/`tts.py` 线程/`gesture.py` 线程内显式 `ctypes.windll.ole32.CoInitializeEx(None, 0x2)`（MTA），全程统一。
- **loopback 抓取**：必须 `get_microphone(id=str(spk.id), include_loopback=True)`（按 name 会命中麦克风端点）。默认输出设备**静音时 loopback 全 0 不报错**——启动自检 `_ensure_audio` 会 `SetMute(0)`，音量 <0.02 才调，正常不动。 运行中连续 8s 峰值 <0.01 会警告、20s 自动回退默认输出（`AUDIO_FALLBACK=1`）。
- **pycaw 方法名**：`GetMasterVolumeLevelScalar/SetMasterVolumeLevelScalar`（不是 `GetVolumeScalar`）；`AudioUtilities.GetSpeakers()` 拿到 `IAudioEndpointVolume`。用完 `del vol, iface, sp` + `gc.collect()` 避免退出时 access violation。
- **gesture 导入顺序**：`import cv2/mediapipe` 必须在**主线程**（`mvp.py` 顶层 `from gesture import`），子线程首次 import 会在 Qt 事件循环起来后死锁；`cap.read()` 会卡，需线程内 COM 初始化 + 强制 `CAP_DSHOW`。
- **摄像头独占**：Windows 默认一个摄像头只给一个进程（腾讯会议/Zoom 占着就读不到）。Win11 26400+ 可开「允许多个应用同时使用照相机」。
- **`edit` 工具别改含反斜杠的 Markdown 链接行**（如 `docs\\交接文档.md`，源码里是字面 `\\`，会匹配不到）——改 README 用临时 Python 脚本或整段 write。
- **笔试四种取图**：整屏（`shift`+双击）/ 窗口（`alt`+双击）/ 框选（`Ctrl+Shift+S`）/ 长截图（`shift+alt`+双击两次）。`Screenshotter` 统一走 `_grab()`（`before_grab/after_grab`），截图前把浮窗 `setWindowOpacity(0)`（`SHOT_HIDE_UI=1`），队列非空时两张间隔 1 秒。
- **框选层不许抢焦点**：`WindowDoesNotAcceptFocus + WA_ShowWithoutActivating`（否则浏览器失焦=切屏）；Esc 不可用，右键取消；框选层自身 `SetWindowDisplayAffinity(0x11)`。
- **浮窗永不抢焦点**：`show()` 用 `WA_ShowWithoutActivating` + `SetWindowPos(HWND_TOPMOST, SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW)`；`_cloak()` 同样带 `SWP_NOACTIVATE`。答案到达只显示不抢焦点（浏览器不会判切屏）。
- **重答热键 `Ctrl+Shift+R`（`retake`）**：面试=重发上一句，笔试=重新截一张；`Ctrl+Shift+G` 笔试=重新识别当前截图（`last_png` 复用，不重新截屏）、面试=强制提交当前文字；`Ctrl+Shift+L` 题目列表（`ui.show_list`）。
- **隐身 5 秒保活 `STEALTH_KEEPALIVE=1`**：`Overlay._stealth_main()` 由 QTimer 每 5s 重设 `SetWindowDisplayAffinity(0x11)` + TOPMOST（`SWP_NOACTIVATE`），状态变化才打日志；新增窗口（如 grid）也要在同一循环里校准。
- **`EXAM_SAFE` 必须在 `GESTURE_ON/MOBILE_ON/TTS_ON` 赋值之后应用**（2026-11-11 修过一次顺序 bug：先关再被 env 覆盖，等于没关）。
- **识别失败不覆盖旧答案**：`on_shot` 里视觉输出为空或以「未识别/没有识别/识别不」开头 → 保留上一题答案，只提示「未识别到题目，请重新框选题目区域」。
- **题型标记**：`_shot_prompt()` 要求第一行输出 `【题型】编程题|选择题|判断题|填空题|技术问答|图形推理|未识别`；`_exam_kind()` 解析。选择题/判断题走 `_exam_tidy()` 压到「题型标记 + 最多 2 行正文（≤90 字）」，别让模型把四个选项都分析一遍。`_looks_unrecognized()` 必须先剥掉 `【题型】` 标记再判断，否则「未识别」守卫会失效。
- **签名校验 `_CODE_SIG_RE` / `_is_coding()`**：编程题缺 `class`/`def`/`func`/`function`/Java 方法签名时，带 `_SHOT_RETRY_HINT` 重试一次；只重试这一种，别对每题都重试。
- **长截图兜底**：`Screenshotter._long()` 拼接失败 → 两段分别入队（间隔 1s）；上半段超时 → 先单独识别上半段；`cancel()` 清 `long_first`。
- **热键默认吞键**：`hotkeys.install(suppress=True)`（`HOTKEY_SUPPRESS=1`）。否则浏览器会收到 `Ctrl+Shift+B`（书签栏）/`Ctrl+Shift+S`（另存为），页面键盘监控也能看到。鼠标手势触发时 `return 1` 吞点击。
- **笔试安全模式 `EXAM_SAFE=1`**：模块级强制 `GESTURE/MOBILE/TTS=0`，窗口隐藏 + 点击穿透，`F8` 显示；只对 `MODE=exam` 生效。
- **控制台反截屏 `CLOAK_CONSOLE=1`**：`_cloak_console()` 对 `GetConsoleWindow()` 设 `0x11`；重定向/无控制台时返回 False 属正常。
- **笔试窗口形态**：默认 `EXAM_GHOST=0` + `EXAM_IDLE=1`——窗口常驻可见，未截图时主区域渲染 `EXAM_IDLE_HELP` 快捷键卡片；截图前后由 `grab_hide()/grab_show()` 负责隐身与恢复。`grab_hide()` 必须先记 `_was_visible` 再 `win.hide()`（不要用 `setWindowOpacity(0)`，DWM 有延迟）；`grab_show()` 只恢复「截图前本来就可见」的窗口，幽灵模式（`EXAM_GHOST=1`）下截图后不得把窗口叫出来。`F8` 在幽灵模式下叫出后不自动消失。
- **Qt 控件跨线程必须走 Bridge signal**：`keyboard`/HTTP/定时器回调在别的线程，直接 `win.show()/hide()` 会被 Qt 静默丢弃（现场表现=热键没反应）。`toggle_visible()/show()/hide()` 都先判 `QThread.currentThread() is app.thread()`，否则 emit `toggle/show_req/hide_req`，主线程执行 `_toggle_main/_show_main/_hide_main`。新增任何 UI 方法照此办理。
- **无边框半透明顶层窗必须自绘底板**：`FramelessWindowHint + WA_TranslucentBackground` 的顶层 `QWidget` 上，`setStyleSheet("QWidget{background:rgba(...)}")` 不保证绘制（实测 `win.grab()` 全透明，现场=只有浅色字浮在壁纸上）。底板由 `Overlay._paint_panel`（`paintEvent`）用 `QPainter.drawRoundedRect` 画，颜色来自主题 `bg` 解析出的 `self._bg`；换主题必须重解析。
- **子控件铺满时，拖动/缩放走事件过滤器**：`QTextBrowser` 盖住整窗，`win.mousePressEvent` 永远收不到。`Overlay` 不是 `QObject`，用 `_Filt(QtCore.QObject)` 包一层装到 `view` / `view.viewport()` / `status` / `thumb` 上；左键=拖动、右下角 20px=缩放、`Ctrl+滚轮`=字号、`Alt+滚轮`=透明度。`scale_step()` 必须同时改窗口尺寸和字号（`_apply_theme`/`_render_main` 都乘 `self.scale`），只改尺寸等于没放大。
- **热键回调要有 wrapper**：`hotkeys.install(cb, log, post)` 包一层，`HOTKEY_DEBUG=1` 打印 `[hotkey] 触发 X`、异常打印 `[hotkey] X 出错 ...`；否则异常被 keyboard 吞掉，排查时看不出到底有没有触发。
- **热键回调必须 `post` 到主线程**：`keyboard` 的低级键盘钩子/`MouseHooks` 的 `WH_MOUSE_LL` 都在原生回调栈里跑，在回调里直接 `win.hide()/show()/quit()` 是重入 Qt 窗口过程，进程会以 `0xC000041D`（`STATUS_FATAL_USER_CALLBACK_EXCEPTION`，现场表现为 `exited with code -1073740771`）直接消失。`mvp.py` 传 `post=ui.post_hotkey`（登记 `_hk_fns` + emit `bridge.hotkey`），`MouseHooks` 只 `queue.put`，由常驻 worker 执行。新增热键一律走这条路。
- **崩溃取证 `clone/run.log`**：`_trace()`（每行 flush，带时间/pid）埋点在 start / overlay ready / before ui.run / exec enter|returned / hotkey / toggle|show|hide / grab_hide|grab_show / stealth tick / render；`faulthandler` 也写同一文件。原生崩溃没有 traceback，只能靠最后一行定位；`start-exam.bat` 非 0 退出会自动 tail 12 行。
- **鼠标手势可配**：`SHOT_CLICKS`(1/2/3)、`SHOT_BUTTON`(left/right/middle/x)、`MouseHooks(mods={...})`；`_kind_for()` 要求修饰键精确匹配。
- **识别回显 `set_thumb`**：`on_shot` 里 `begin_answer` 后立刻把**原图**（非 prepare 后）经 `bridge.thumb` 贴进浮窗，等比缩到 240×100 内；下一张截图或新答案覆盖。任意线程可调，`_set_thumb_main` 在 Qt 主线程做。
- **图形准备页 `grid.py`**：`Grid` 延迟创建（第一次 `Ctrl+Alt+G` 才 import PySide6）；全屏虚拟桌面并集；网格 64px + 中线 + 涂鸦；flags `FramelessWindowHint|WindowStaysOnTopHint|Tool|WindowDoesNotAcceptFocus` + `WA_TranslucentBackground|WA_ShowWithoutActivating`（**不抢浏览器焦点**）；左键画线/右键清空；显示时自身 `SetWindowDisplayAffinity(0x11)`。热键 `ctrl+alt+g` → `cbs["grid"]` → `ui.toggle_grid()` → `bridge.grid` → `_grid_main()` 懒 import。
- **DOM 读题走 CDP，不要指望 UIA**：Chrome 只在检测到屏幕阅读器时才向 UIA 暴露正文，普通窗口只能读到地址栏。`dom.py` 的 `read_question_ex()` 先连 `DOM_CDP`（默认 `http://127.0.0.1:9223`）用 `Runtime.evaluate` 取 `innerText`，失败才走 UIA。`open_debug_browser()` 用独立 profile `clone\browser-data` + `--force-renderer-accessibility` 拉起；**只读，不注入、不改 DOM**。
- **方向键热键不能吞**：`hotkeys.install()` 里 `loose={"shift+up","shift+down","shift+left","shift+right"}` 这些组合 `suppress=False`——输入框/代码编辑器要用 Shift+方向键选字。其它热键默认吞（`HOTKEY_SUPPRESS=1`）。
- **看护进程 `guardian.py`**：`subprocess.Popen(stdout=PIPE, stderr=STDOUT, text=True, encoding="utf-8")`；退出码 0 结束，非 0 按 `min(5, GUARDIAN_DELAY*1.5**(n-1))` 退避重启，`GUARDIAN_MAX`（0=不限）；Ctrl+C 先 terminate 子进程。**`start-exam.bat` 现在默认走 guardian**（`plain` 只跑一次、`guard` 强制守护），重启事件同时写 `run.log` 的 `[guard:<pid>]` 行。
- **崩溃自愈三件套**：① guardian 进程级重启；② `_install_excepthooks()` 接管 `sys.excepthook`/`threading.excepthook`，普通异常只写 `run.log` 不带走进程；③ `ui_state.json` 每 10s + 退出时存 `x/y/w/h`，`_restore_geometry()` 启动恢复（屏外坐标丢弃）。
- **整屏共享时控制台必须藏**：conhost 窗口跨进程设不了 WDA，`CONSOLE_MIN` 只是最小化（任务栏仍有按钮），所以默认 `CONSOLE_HIDE=1`（`ShowWindow(hwnd,0)`）；托盘默认 `TRAY=0`。要看日志就开 `clone\run.log`。
- **窗口隐藏后的三条找回路**：`F8` / `Ctrl+Shift+B` / `Ctrl+Alt+S`；再启动一次 `mvp.py` 会连 `127.0.0.1:19399`（`SHOW_PORT`）握手，已有实例就发 `show` 并自己退 0。改这个端口要同时改 `.env` 与文档。
- **WDA 结论以 `clone/gdi_alpha_test.py` 为准**：Win11 26200 上 `WDA_EXCLUDEFROMCAPTURE(0x11)` 对 WGC/DXGI **和 GDI BitBlt** 都生效（不透明窗口设/取消 WDA 的截图对照可复现）；半透明窗口在 BitBlt 里本来就不出现。旧的 `wda_ctl.py` / §37.1「GDI 挡不住」结论已作废，不要再引用。Win10 <2004 不支持 0x11。
- **`grab_hide/grab_show` 的语义**：按可见性恢复，不是按透明度。`grab_show()` 恢复 `self.opacity`（不要写死 1.0），并只在 `_was_visible` 为真时 `show()`。
- **`grab_hide/grab_show` 必须跑在主线程**：截图链路由鼠标钩子线程触发，非 GUI 线程直接 `win.hide()`/`processEvents()` 会让进程以 `0xC000041D`（`STATUS_FATAL_USER_CALLBACK_EXCEPTION`）消失。跨线程只 `emit` 信号（`grab_hide_req`/`grab_show_req`），隐藏用 `_grab_evt.wait(0.8)` 阻塞到生效再抓图。回归：`grab_thread_test.py`、`shot_thread_test.py`。
- **答案与解析必须分段**：提示词要求可抄内容以 `【答案】` 开头、解释以 `【解析】` 开头；`_md_html()` 负责把两者渲染成不同样式，别再让模型把「答案：X，因为…」写在一行。

- **VAD 常量**：`SR=16000`、`BLOCK=1600`、`SILENCE_RMS=0.006`、`SILENCE_HANG=0.6`、`MIN_SPEECH=0.5`；早触发 `PARTIAL_STEP=1.2`。
- **ASR 幻觉过滤**：段级丢 `no_speech_prob>0.55`/`avg_logprob<-1.1`；`_is_hallucination()` 三重判：①≤24 字命中已知尾巴「请用简体中文输出/字幕由/amara.org/谢谢观看」；②`re.search(r"(.)\1{5,}")` 单字刷屏；③长度≥8 且字符多样性 <0.4。**别用「时长 <1.6s 就丢」这类概率/时长门槛**——会误杀 1.4s 的正常 partial（早触发靠它）。

## Known Issues / Gotchas

- 默认输出设备静音/音量为 0 → loopback RMS=0.0，不报错（先 `python setvol.py 0.8` 或 `python devices.py` 看现状）。
- `gesture` 模型文件在 `models/`，首次下载走 storage.googleapis.com；`GESTURE_DEBUG=1` 开 faulthandler。
- relay 的 `/v1/models` 返回空列表，但 chat 可用——别用 models 列表判断 relay 是否可用，直接发 chat 或看 `/api` 连通。
- 视觉模型关思考用 `VISION_EXTRA_JSON`，普通 LLM 用 `LLM_EXTRA_JSON`，两者独立。
- `features_test.py` 里发手机请求必须带 `?t=<token>`，否则 403；页面路径 `/`、状态 `/api/state`、指令 `/api/cmd`。

## Reference Docs

- `docs/交接文档.md` — 开发交接（采集→VAD→ASR→LLM 全链路结论）
- `docs/开发日志.md` — 逐日开发日志（含各模块实测数据）
- `docs/面试侠逆向报告.md` — 商业客户端逆向结论（服务端能力边界）
- `clone/README.md` — 功能表 / 配置说明 / 已知坑
- **鼠标双击手势有判定窗口**：`hotkeys.MouseHooks(interval=SHOT_INTERVAL 0.85s, dist=SHOT_DIST 24px)`。
  Windows 默认双击速度 500ms，阈值必须比它大（旧值 0.45s 导致用户"双击没反应、只有 Ctrl+Shift+S 能用"）。
  任何"手势拆不动"的反馈，先让用户改用键盘兜底 `Ctrl+Shift+1/2/3`（整屏/窗口/长截图），再让他调 `SHOT_INTERVAL`。
- **热键必须按“实际键名”注册**：`keyboard` 按键名匹配，按住 Shift 时 `1/2/3/=/-//` 会变成 `!/@/#/+/_/?`。
  截图键因此注册 `ctrl+shift+!`/`@`/`#`（界面显示 `Ctrl+Shift+1/2/3`）；缩放用 `ctrl+alt+↑/↓`；帮助用 `Ctrl+Shift+H`。
  不要注册 `ctrl+shift+数字`（匹配不上，且数字扫描码与方向键/小键盘冲突，会误触发截图）；`Alt+Shift` 是输入法切换，别用。
  新增/修改热键后，必须用「按下→延时 60ms→释放」的跨进程方式实测，并同步 `docs/快捷键.md`、`hotkeys.HELP_TEXT`、
  `mvp.EXAM_IDLE_HELP`、`clone/README.md`、根 `README.md`、`docs/操作步骤说明.md`；没测通的组合一律不写进文档。
