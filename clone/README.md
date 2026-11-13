# msx-clone — 面试侠同类 MVP

> 接手开发先读 [`../docs/交接文档.md`](../docs/交接文档.md)：现状、环境、踩坑、路线图、验收标准都在里面。

功能对齐 <https://mianshixia.cn/docs> 的桌面端能力（本地实现，不需要账号）：

| 功能 | 状态 | 用法 |
|---|---|---|
| 面试：系统音频 → 问题 → 流式答案 | ✅ | `start.bat`（`MODE=interview`） |
| 笔试：截图 → 视觉模型 → 答案 | ✅ | `start-exam.bat`（`MODE=exam`，不采集音频） |
| 题型自动分流（编程/选择/判断/填空/问答/图形） | ✅ | 模型第一行输出 `【题型】…`，选择/判断题自动压到 2 行内 |
| 编程题签名校验 + 缺签名自动重试 | ✅ | 代码块里没有 `class`/`def` 时带模板提示重试一次 |
| 早触发（问题没说完就先答） | ✅ | `EARLY_ASK=1` |
| 防截屏 + 任务栏/Alt-Tab 隐藏 + 伪装标题 | ✅ | `CLOAK=1`、`WIN_TITLE=Settings` |
| 截图出答案（整屏 / 窗口 / 框选 / 长截图） | ✅ | `Ctrl+Shift+1/2/3` 或 Shift+双击 / Alt+双击 / Shift+Alt+双击；`Ctrl+Shift+S` 框选 |
| 手势可配（点击次数 / 鼠标键 / 双击窗口） | ✅ | `SHOT_CLICKS=2`、`SHOT_BUTTON=left`、`SHOT_INTERVAL=0.85`、`SHOT_DIST=24` |
| 笔试模式（语言、力扣/ACM） | ✅ | `MODE=exam`、`EXAM_LANG`、`EXAM_STYLE`；首次启动进准备页 |
| 笔试安全模式（不碰摄像头/端口/语音） | ✅ | `EXAM_SAFE=1`：窗口默认隐藏+点击穿透，`F8` 显示 |
| 手势可配（点击次数 / 鼠标键 / 修饰键） | ✅ | `SHOT_CLICKS=2`、`SHOT_BUTTON=left`、`SHOT_INTERVAL=0.85`、`hotkeys.MouseHooks(mods=...)` |
| 热键吞掉不外漏 | ✅ | `HOTKEY_SUPPRESS=1`：浏览器收不到 Ctrl+Shift+B/S 等 |
| 控制台反截屏 | ✅ | `CLOAK_CONSOLE=1`：日志本地可见，共享/录屏不可见 |
| 隐身 5 秒保活 | ✅ | `STEALTH_KEEPALIVE=1`：每 5 秒重设 WDA 反截屏（对齐官方 v0.3.100） |
| 窗口形态（默认常驻） | ✅ | `EXAM_GHOST=0` + `EXAM_IDLE=1`：未截图时显示快捷键卡片；截图瞬间自动隐身、抓完恢复。可选 `EXAM_GHOST=1` 幽灵窗（启动隐藏、答案出现、N 秒后消失） |
| 题目列表 + 缩略图随题切换 | ✅ | `Ctrl+Shift+L` 看第 N 题/摘要/字数，`Ctrl+Shift+↑/↓` 切换时缩略图跟着换 |
| 本地题库原样命中 | ✅ | `clone\题库.csv` |
| 回答风格（极简/标准/详细/大纲） | ✅ | `ANSWER_STYLE` |
| 快捷键全套 | ✅ | `Ctrl+Shift+H` 看说明 |
| 手机联动（网页看答案 + 遥控） | ✅ | 终端打印二维码，`MOBILE=1`；`MOBILE_HIDE=1` 第一题后自动藏窗口 |
| 长问句优化（等说完再答） | ✅ 默认关 | `LONG_Q=1` |
| 语音播报（笔试第二机位） | ✅ | `TTS=1` |
| 动作捕捉（扶眼镜 / 眨两下） | ✅ | `GESTURE=1`、`GESTURE_MODE=glasses\|blink` |
| 视觉模型 | ✅ | `VISION_MODEL`，默认 `deepseek-v4.1-flash` |
| 小窗样式（极暗 / 蓝灰 / 大字） | ✅ | `THEME=dark\|blue\|large`，`Ctrl+Alt+Y` 切换 |
| 长时间无声音自动回退 | ✅ | `AUDIO_FALLBACK=1`：8s 提示、20s 切默认输出 |
| ⚡ 速答（一句话先上屏，完整答案覆盖） | ✅ | `QUICK_ANSWER=1` |
| 资料库（岗位/简历/知识库/提示词模板） | ✅ | `clone\资料\`，`profile.py` 本地解析 |
| 回答档位（灵动 / 睿智） | ✅ | `LLM_PROFILE=speed\|natural` |
| 外语面试翻译对照 | ✅ | `TRANSLATE=1`（英/日/韩先给中文对照） |
| 题库 Excel + 表头自动跳过 | ✅ | `题库.xlsx` 或 `BANK_CSV`，`序号/问题,答案` 自动识别 |
| 截图识别回显（缩略图确认没截错） | ✅ | 截到的原图缩略图贴进浮窗（240×100 内等比） |
| 图形准备页（网格+涂鸦，行测图形题） | ✅ | `Ctrl+Alt+G`：全屏网格+中线，左键画线/右键清空，不抢浏览器焦点 |
| DOM 读题（不截图，直接读页面文字） | ✅ | `Ctrl+Shift+D`：CDP 优先（`--remote-debugging-port=9223`），UIA 兜底；`DOM_AUTO=1` 自动读题 |
| 追问预判 | ✅ | `Ctrl+Shift+U`：列 3 个最可能的追问 + 一句回答要点 |
| 窗口大小 / 迷你窗 | ✅ | 默认 560x400；右下角「小」或 `Ctrl+Alt+M` 切 430x250 迷你窗（字号同步 -2），再按还原；右下角「隐」或 `F8` 隐藏 |
| 隐藏 / 退出 | ✅ | 「隐」按钮或 `F8` 隐藏；叫回来按 `F8` / `Ctrl+Shift+B` / `Ctrl+Alt+S`，或**再双击一次 `start-exam.bat`**（已有实例会把窗口弹出来）；`Ctrl+Shift+Q` 两下退出；日志看 `clone\run.log` |
| 窗口移动 / 缩放 | ✅ | 鼠标左键拖动移动、拖右下角缩放（QTextBrowser 铺满也能拖）；`Ctrl+滚轮` 字号、`Alt+滚轮` 透明度；`Shift+方向键` 移动 20px，`Ctrl+Alt+↑/↓` 缩放 |
| 看护进程（崩溃自动重启） | ✅ | **`start-exam.bat` 默认就走守护**；`plain` 只跑一次，`guard` 强制守护。崩溃 0.5s 后重启，窗口位置/大小自动恢复（`ui_state.json`） |

> 检测风险与规避见 [`../docs/检测风险评估.md`](../docs/检测风险评估.md)；
> 操作步骤见 [`../docs/操作步骤说明.md`](../docs/操作步骤说明.md)；
> 全部热键速查见 [`../docs/快捷键.md`](../docs/快捷键.md)。
> 笔试/面试时**别用鼠标点浮窗**（会让浏览器失焦触发切屏判定），全程热键，或按 `F9` 开点击穿透。
> `Ctrl+Shift+S` 框选时不会抢焦点，浏览器不会因此判切屏；截图前浮窗会自动透明（`SHOT_HIDE_UI=1`）。
> 答案到达时浮窗只显示不抢焦点；识别失败（模型回「未识别到题目」）不会覆盖上一题的可用答案，按 `Ctrl+Shift+R` 重截。
> **窗口形态**（默认常驻可见）：`EXAM_GHOST=0` + `EXAM_IDLE=1`。没截图时主区域显示快捷键卡片（含「Ctrl+Shift+Q 连按两次退出」）；按截图键的瞬间窗口自动 `hide()`（抓出来的图里没有自己），抓完恢复原状；窗口不会自动消失；共享/录屏里对方看不到这个窗口（WDA `0x11`，本机 Win11 对 WGC 与 GDI 均实测生效）。
> 想要更隐蔽可改 `EXAM_GHOST=1`：启动就不显示，答案到达才出现，`GHOST_HIDE_AFTER` 秒后自动消失，`F8` 随时叫出。
> **整屏共享**：控制台默认直接隐藏（`CONSOLE_HIDE=1`，任务栏也不留按钮）、托盘默认不建（`TRAY=0`）；日志只写 `clone\run.log`。这样整屏采集里除了桌面只有浮窗，而浮窗被 WDA 剔除。
> **自愈**：`start-exam.bat` 默认守护，子进程崩溃（含 `0xC000041D`）后 0.5s 拉起，窗口几何从 `ui_state.json` 恢复；重启记录写在 `run.log` 的 `[guard:<pid>]` 行。
> **LLM relay 断了怎么办**：答题依赖 `127.0.0.1:19300`（智能交付 → forwarder）。先在智能交付客户端里打开/新建一个会话，再跑 `powershell -NoProfile -ExecutionPolicy Bypass -File .\relay-restore.ps1 -WaitSeconds 60`，看到 `HEALTHY` 即恢复。
> **默认窗口 800x620**；小于 560x400 的存档（迷你态）不再还原，避免下次启动还是个小窗。
> **看不清 / 想挪位置**：鼠标左键按住窗口任意位置拖动即可移动，拖右下角 20px 内改大小；`Ctrl+滚轮` 直接放大字号（窗口同步放大），`Alt+滚轮` 调透明度；觉得字小可以先 `Ctrl+Alt+Y` 切到「大字清晰」主题。底板是自绘的深色圆角块（`_paint_panel`），不会只剩一层白字浮在壁纸上。
> **关不掉 / 找不到窗口**：控制台默认是隐藏的，浮窗也没有关闭按钮。双击 `stop-exam.bat`（或桌面的「关闭msx-clone」快捷方式）即可把 mvp + guardian + 宿主 cmd 全部清掉；程序内退出是 `Ctrl+Shift+Q` 连按两次。
> 实现要点：`grab_hide()` 记录 `_was_visible` 后 `win.hide()`；`grab_show()` 只恢复「截图前本来就可见」的窗口；所有 `show/hide/toggle` 先判线程，跨线程走 `bridge.toggle/show_req/hide_req`（Qt 控件不能在 hook 线程动）。
> 热键同理：`keyboard` / 鼠标钩子在原生回调里触发，**一律 `post_hotkey()` 转投主线程**再执行；钩子里直接 `hide()/quit()` 会让进程以 `0xC000041D` 消失。

## 启动（Windows，双击 bat）

只有两个入口（和官网一致：一个客户端，面试听声音、笔试看截图）：

| 文件 | 场景 | 链路 / 就绪时间 |
|---|---|---|
| `start.bat` | 面试 | loopback → VAD → ASR → 作答；约 20s（要加载 ASR） |
| `start-exam.bat` | 笔试 | **只截图 → 视觉模型 → 答案**；不采集音频、不加载 ASR，约 3s |
| `start-exam-compat.bat` | 笔试（兜底） | 同上，但关掉 `STEALTH_KEEPALIVE` 与 `CLOAK_CONSOLE`；对付 `exited with code -1073740771` |

> 崩溃取证：程序把每一步写进 `clone\run.log`（时间 + pid + 动作），`start-exam.bat` 非 0 退出时自动打印最后 12 行。
> 看到 `exited with code -1073740771`（`0xC000041D`，用户回调里未捕获的异常）先翻 `run.log` 最后几行，
> 再换 `start-exam-compat.bat` 试；两档都能截屏出答案，区别只是少一个 5 秒保活循环和控制台隐身。

> 第一次跑 `start-exam.bat` 会先进准备页（18 种语言 + 力扣/ACM），写回 `.env` 的 `EXAM_LANG` / `EXAM_STYLE`；
> 以后要改：`start-exam.bat setup`（或 `python exam_setup.py`）。
> 自检/无界面不是日常入口：`python selftest.py deps|e2e|llm`、`python mvp.py --no-ui`。
> 根目录 `E:\aaa_msx\` 下也有同样的两个入口，只是转发到本目录，双击哪个都一样。

笔试就绪后日志是这两行（没有 `[capture]` / `[asr]` 才对）：

```
[mode] exam｜伪装标题 'Settings'｜语音播报 关
[exam] 截图作答：Shift+双击 整屏 / Alt+双击 窗口 / Ctrl+Shift+S 框选 / Shift+Alt+双击 长截图
```

面试就绪是 `[llm] 预热完成 2.19s` + `[capture] 采集中: ...` + `[asr] local:faster-whisper-base@cuda`。

手机联动默认关（`MOBILE=0`，不再打印二维码）；要第二机位再改 `.env`。

当前模型（写死在 `.env`，可以改）：

- 答题 / 视觉：**智能交付 relay 的 `deepseek-v4.1-flash`**，`http://127.0.0.1:19300/v1`，
  关思考（`LLM_EXTRA_JSON={"thinking":{"type":"disabled"}}`）+ 保活（`LLM_WARM=1`），实机正文首字 0.83–1.45s。
  relay 由 opencode 提供，**用之前先开着 opencode**。
- ASR：**本地 `faster-whisper-base` @ CUDA**（relay 无 `/v1/audio/transcriptions`，语音识别不能走它）。

> bat 必须 **ASCII + CRLF**：cmd.exe 按 GBK 解析 UTF-8 批处理，中文注释会让整行错位（报 `'保活' 不是内部或外部命令`）；
> 只有 LF 换行也会让 `rem` / 括号块解析错乱。要加中文说明请写在 README，不要写进 bat。

`mvp.py` 是主程序，周边能力拆成小模块：

```
WASAPI loopback（系统输出，即面试官声音）
  -> 16k 单声道 -> 能量 VAD（partial / spec / final 三级）
  -> ASR（本地 faster-whisper）
  -> 问题判定（规则）-> 题库精确/相似命中？
  -> LLM 流式（智能交付 relay / DeepSeek / 任意 OpenAI 兼容端点）
  -> 无边框置顶透明窗（防截屏 + 伪装）/ 手机网页 / 耳机语音播报

截图（PIL ImageGrab）-> 视觉模型 -> 思路 + 代码
```

| 文件 | 作用 |
|---|---|
| `mvp.py` | 采集、VAD、ASR、Brain、Overlay、main |
| `profile.py` | 岗位/简历/知识库/提示词 → 注入 system prompt（本地解析，`clone\资料`） |
| `shot.py` | 整屏/窗口/框选/长截图，`Screenshotter` 串行排队（截图前自动隐藏浮窗） |
| `bank.py` | 题库 CSV 读取 + 归一化相似匹配 |
| `tts.py` | SAPI 朗读，代码块自动跳过 |
| `mobile.py` | 局域网手机页（二维码 + token）+ 遥控指令 |
| `hotkeys.py` | 全局热键 + 鼠标手势（次数/键/修饰键可配，触发时吞点击） |
| `exam_setup.py` | 笔试准备页（终端版）：语言 + 力扣/ACM 写回 `.env` |
| `grid.py` | 图形准备页：全屏网格 + 涂鸦层（`Ctrl+Alt+G`，不抢焦点，自身 WDA） |
| `dom.py` | DOM 读题：CDP（`127.0.0.1:9223`）优先，UIA 兜底；`extract_question/looks_like_question` |
| `guardian.py` | 看护进程：拉起 `mvp.py`，非 0 退出按 1.5/3/5s 退避重启，日志 `guardian.log` |
| `selftest.py` | 分层自检 deps / capture / asr / e2e / llm |
| `features_test.py` | 题库 + 视觉 + 手机 联调自检 |
| `live_test.py` | 无界面全链路：播 wav → 抓回 → 出答案 |

## 安装

```powershell
Set-Location E:\aaa_msx\clone
python -m pip install -r requirements.txt
```

只用 numpy + openai 也能跑（没有 PySide6 时降级为控制台输出，没有 faster-whisper 时走云端转写）。

## 先自检，别直接进会议

```powershell
python selftest.py deps        # 依赖、音频设备、loopback、key、relay
python selftest.py e2e -w "C:\Program Files\msx-client\resources\self-test-interviewer.wav"
```

`e2e` 把一段"面试官提问"的 wav 从默认输出设备播出来，再从系统回环里抓回来，走完 VAD + ASR。
这一步能过，说明"听得到 + 听得懂"没问题，剩下的只有 LLM。

**已知坑：默认播放设备被静音时，loopback 抓到的全是 0（RMS=0.0000），但不会报错。**
`AUDIO_AUTOFIX=1`（默认）会在启动时自动取消静音；音量低于 2% 才补到 30%，正常音量不动。
仍然抓不到就手动查：

```powershell
python -c "import ctypes;from pycaw.utils import AudioUtilities;from pycaw.pycaw import IAudioEndpointVolume as V;from comtypes import CLSCTX_ALL;sp=AudioUtilities.GetSpeakers();v=ctypes.cast(sp._dev.Activate(V._iid_,CLSCTX_ALL,None),ctypes.POINTER(V));print(v.GetMute());v.SetMute(0,None)"
```

## 配置

复制 `.env.example` 为 `.env` 后改，`mvp.py` 启动时自动读（系统环境变量优先）。

**A 方案（默认，走本机「智能交付」relay，不需要外网 key）**：

```ini
OPENAI_BASE_URL=http://127.0.0.1:19300/v1
OPENAI_API_KEY=local-yonyou-relay
LLM_MODEL=deepseek-v4.1-flash
LLM_REASONING_EFFORT=
LLM_EXTRA_JSON={"thinking":{"type":"disabled"}}
ASR_MODEL=faster-whisper-base
ROLE=后端工程师，5 年经验，主做 Java/Spring Cloud
RESUME=负责订单中心重构，QPS 800->6000；主导分库分表
MSX_MODELS_DIR=E:\aaa_msx\models
```

**B 方案（直连 DeepSeek 官方）**：`OPENAI_BASE_URL=https://api.deepseek.com/v1`、`OPENAI_API_KEY=sk-...`、`LLM_MODEL=deepseek-flash`、去掉 `LLM_EXTRA_JSON`（这条对官方 API 无效，会自动退回默认模式）。

| 档位 | 思考首字 | 正文首字 |
|---|---|---|
| flash 默认（reasoning 开） | 3.5–4.7s | 5.4–6.1s |
| flash + `reasoning_effort=minimal` | 1.2–2.2s | 2.3–3.9s |
| **flash + `thinking:disabled`** | 无思考 | **冷 3.8s / 热 0.37–0.78s** |
| GLM-5.3 默认 | 0.5–0.9s | 1.2–2.4s |

`thinking:disabled` 是当前最快的一条路，答案质量实测没退化（`bench_llm2.py` 有原始数据）。
但这条链路冷热差别极大（3.76s → 0.37s），所以 `LLM_WARM` 默认开：启动时打一发 1 token 请求，
之后空闲超过 50s 自动补一发，保证面试官开口时连接是热的（有请求在跑时不会插进去抢队列）。

离线模型（已下好，无需联网）：`E:\aaa_msx\models\faster-whisper-{tiny,base}`，仓库名会自动映射到本地目录。

声音设备：`AUDIO_DEVICE` 填输出设备名的子串（如 `耳机`、`Realtek`），留空用系统默认输出。
**面试时把会议软件的扬声器设成同一个设备**（用耳机就选耳机），否则 loopback 抓不到。

### 资料目录（对应官网「岗位 / 简历 / 知识库 / 提示词模板」，本地解析，不上传）

```
clone\资料\
├─ 简历.md / 简历.pdf / 简历.docx      # 只 1 份，≤3MB，建议别用扫描图
├─ 知识库\JD.md、项目.md               # 最多 2 份，≤3MB（JD、项目文档、技术方案）
├─ 提示词_面试.txt                     # ≤2000 字，追加到系统指令之后
└─ 提示词_笔试.txt
```

- 用 `MSX_PROFILE_DIR` 改目录；`profile.py` 启动时解析，日志会打印 `[profile] ...`。
- 简历/知识库进上下文（各截断 4000 / 2500 字），提示词进 `【用户固定要求，必须遵守】` 段。
- `.doc` 不解析（老二进制格式），另存 `.docx` 即可。
- PDF 里的汉字有时是「康熙部首」编码（`⻚`/`⻓` 等），`profile.py` 会 NFKC + 映射表归一，不用手动处理。
- 依赖：`pypdf`（PDF）、`python-docx`（Word），已列进 `requirements.txt`。
- 岗位仍然用 `ROLE`（如 `后端工程师，5 年经验`），会同时影响回答侧重点。

### 速答 / 档位 / 翻译

| 变量 | 默认 | 说明 |
|---|---|---|
| `QUICK_ANSWER` | `1` | 先出一句 ≤40 字速答（`⚡ 速答：…`），完整回答到达即覆盖；实测只让首字 +0.15s |
| `LLM_PROFILE` | `speed` | `speed`=灵动（关思考，最快）；`natural`=睿智（`reasoning_effort=high`，更口语但慢） |
| `TRANSLATE` | `1` | 英/日/韩问题先给一行「【中文对照】」，再作答 |

## 操作

| 热键 | 作用 |
|---|---|
| `F8` / `Ctrl+Shift+B` | 显示/隐藏窗口 |
| `F9` | 点击穿透 |
| `F10` / `Ctrl+Alt+=` `Ctrl+Alt+-` | 透明度 |
| `Ctrl+Alt+Y` | 切换样式（极暗/蓝灰/大字） |
| `Shift+方向键` | 移动窗口 |
| `Ctrl+Alt+↑` `Ctrl+Alt+↓` | 缩放 |
| 鼠标滚轮 | 答案上下滚动 |
| `Ctrl+Shift+G` | 笔试=重新识别当前截图 / 面试=强制提交当前文字 |
| `Ctrl+Shift+R` | 重答上一题（面试=重发上一句，笔试=重新截一张） |
| `Ctrl+Shift+L` | 题目列表（再按返回当前答案） |
| `Ctrl+Shift+X` | 取消当前截图/作答（已出答案保留） |
| `Ctrl+Shift+P` | 钉住 |
| `Ctrl+Shift+↑` `Ctrl+Shift+↓` | 上一题 / 下一题 |
| `Ctrl+Shift+C` | 复制答案 |
| `Ctrl+Shift+H` | 热键说明 |
| `Ctrl+Shift+Backspace` | 清屏 |
| `Ctrl+Shift+Q` | 退出（3 秒内连按两次） |
| `Ctrl+Alt+G` | 图形准备页：全屏网格+涂鸦（左键画线，右键清空，再按一次隐藏） |
| `Ctrl+Shift+D` | DOM 读题：从浏览器页面直接取题干（不截图；CDP 优先，UIA 兜底） |
| `Ctrl+Shift+U` | 追问预判：列 3 个最可能的追问 + 一句要点，追加在当前答案后 |

鼠标手势：`Shift+双击` 整屏截图；`Alt+双击` 窗口截图；`Shift+Alt+双击` 长截图（60 秒内再双击一次，右键/Esc 取消）。
双击判定窗口 0.85s / 24px（`SHOT_INTERVAL`、`SHOT_DIST`）。**手慢或触控板就用键盘版：`Ctrl+Shift+1` 整屏、`Ctrl+Shift+2` 窗口、`Ctrl+Shift+3` 长截图**——走键盘钩子，一定生效。

## 关键实现点

| 点 | 说明 |
|---|---|
| loopback | `soundcard.get_microphone(id=str(speaker.id), include_loopback=True)` —— **必须用 id，不能用 name**，同名时 name 会命中麦克风端点 |
| 采样 | 直接让 WASAPI 重采样到 16k 单声道；失败自动退 48k + 线性重采样 |
| VAD | 自适应噪声底 + 2.5 倍阈值 + 600ms hangover；`SILENCE_RMS` 在嘈杂环境调高 |
| 断句 | 语音段 ≥0.5s 才送 ASR，避免咳嗽/键盘声触发 |
| 问题判定 | 规则命不中就不调 LLM，省 token；误判多时换 7B 分类模型 |
| 流式 | `stream=True` 逐 delta 推到 UI，首字出现即开始念 |
| 早触发 | 不必等整句说完：说话中每 `PARTIAL_STEP`(1.2s) 识别一次，命中疑问词就先发 LLM；静音 `SPEC_HANG`(0.3s) 再抢发一次「预断句」；正式断句 `SILENCE_HANG`(0.6s) 时若文本对得上就沿用已在生成的答案，对不上才重问 |
| 题库 | 归一化（去语气词/标点）后 `difflib` 相似度 ≥ `BANK_THRESHOLD`(0.86) 直接原样出答案，不走 LLM |
| 截图 | `ImageGrab.grab(all_screens=True)`；窗口截图用 `WindowFromPoint` + `GetAncestor(GA_ROOT)`；不走键盘以免被笔试平台记录 |
| 题型分流 | 视觉模型第一行输出 `【题型】…`；选择题/判断题由 `_exam_tidy()` 压到「答案 + 一句依据」，最多 2 行 / 90 字 |
| 答案/解析分色 | 提示词强制「可直接抄的答案」以 `【答案】` 开头、思路依据以 `【解析】` 开头；`_md_html()` 把前者渲染成青蓝高亮块、后者渲染成灰蓝小字，块级 div 不额外撑空行 |
| 截图隐身 | `grab_hide()/grab_show()` 从鼠标钩子线程调用时只 `emit` 信号切回 GUI 线程，隐藏用 `_grab_evt.wait(0.8)` 等生效后再抓图；**禁止在工作线程直接碰 QWidget**（否则进程以 `0xC000041D` 消失） |
| 签名校验 | `_CODE_SIG_RE` 认 `class`/`def`/`func`/`function`/Java 方法；编程题没签名就带 `_SHOT_RETRY_HINT` 重试一次，仍失败才报未识别 |
| 长截图兜底 | 拼接失败时上下两段分别识别（间隔 1s）；上半段超时也先单独识别，不丢内容 |
| 识别回显 | 截到的原图缩略图贴进浮窗（240×100 内等比），一眼确认没截错；下一张或新答案会覆盖 |
| 图形准备页 | `Ctrl+Alt+G` 全屏网格（64px）+ 中线 + 涂鸦层；`WindowDoesNotAcceptFocus+WA_ShowWithoutActivating` 不抢浏览器焦点，自身 WDA 0x11 不进录屏 |
| 视觉 | 图片以 base64 data URL 送 `VISION_MODEL`，不进对话上下文，只留「（上一轮是截图提问）」占位，省 token |
| 手机 | 局域网 HTTP + `?t=<token>` 校验；只下发内容，只接收 `[a-z_]+` 遥控指令 |
| 防截屏 | `SetWindowDisplayAffinity(hwnd, 0x11)`。本机实测（`gdi_alpha_test.py`，Win11 26200）：不透明红窗未设 WDA 时 `ImageGrab` 截到 `(255,0,0)`，设 0x11 后抓到背景，关掉 WDA 又变红——WGC/DXGI 与 GDI BitBlt 都被挡住；半透明窗口在 BitBlt 里本来就不出现（双保险）。Win10 &lt;2004 不支持 0x11 |
| 点击穿透 | `WS_EX_LAYERED \| WS_EX_TRANSPARENT`，热键来回切 |
| 行为日志 | 页面只记得到 `blur/visibilitychange`、`paste`、`keydown`、`mousemove`。截图是 OS 层 GDI `BitBlt`（浏览器无感知）；`HOTKEY_SUPPRESS=1` 让页面收不到热键；浮窗 `SWP_NOACTIVATE` 从不抢焦点。真正会被记的是用户自己切屏/复制粘贴/秒选。考场配置 `SHOT_MOUSE=0` 纯键盘操作，见 `docs/开发日志.md` §46 |
| 伪装 | `SetWindowTextW(hwnd,"Settings")` + 不建任务栏按钮（`WS_EX_TOOLWINDOW`），Alt-Tab 不可见 |
| 不弹窗 | `mvp.py` 顶部 `_quiet_os_errors()`（import 时执行）：`SetErrorMode(0x8003)` 关 GPF/硬错误框 + `HKCU\...\Windows Error Reporting\DontShowUI=1`；`start-exam.bat` 另外把 toast 关掉（`NOC_GLOBAL_SETTING_TOASTS_ENABLED=0`），`stop-exam.bat` 恢复为 1。详见 `docs/开发日志.md` §50 |

## 延迟预算（本机实测：RTX 4050 + CPU int8）

6.8 s 的一段提问，单次转写耗时（`bench_asr.py`）：

| 模型 | 设备 | 加载 | 单次转写 | 识别质量 |
|---|---|---|---|---|
| tiny | cpu | 0.57s | 0.80s | 「面试关」「字我介绍」——有错字 |
| base | cpu | 1.14s | 1.60s | 全对 |
| base | **cuda/fp16** | 0.92s | **0.21s** | 全对 |
| small | cpu | 6.85s | 4.4s | 全对但太慢 |

实测端到端（`live_test.py`，base@cuda + 关思考的 flash，`live.log`）：

```
[预断句 0.22s → 提前发问] 你好,我是今天的面试官,先请你用一分钟做个自我介绍。
[听到 0.19s] 你好,我是今天的面试官,先请你用一分钟做个自我介绍。
[早触发命中，沿用已出的答案]
[早触发 总 2.18s，正文首字 0.90s]
```

即：面试官最后一个字落下 → **0.2s** 预断句 + 0.2s 转写就先发了请求 → **0.9s** 屏幕出第一个字。
这是「问题没说完就开始写答案」换来的，代价是极端情况下要重问一次。

截图链路：`ImageGrab` 整屏 0.073s，视觉模型（flash 关思考）首字 1.4s / 全文 3.4s。

```powershell
python bench_asr.py -w e2e_capture.wav -m E:\aaa_msx\models\faster-whisper-base -d cuda
python bench_llm2.py             # 各家模型/思考档位的首字延迟对比，结果写 bench_llm2.log
python features_test.py          # 题库 + 视觉 + 手机页
python exam_e2e.py               # 笔试两张题图：编程题签名沿用 + 选择题短答
python exam_logic_test.py        # 题型标记 / 短答压行 / 缺签名重试（假 Brain，不联网）
python exam_ui_test.py           # 题目列表 / 缩略图随题切换 / 重识别 / 隐身保活 / 移动
python dom_test.py               # DOM 读题：离线样例 + CDP 实时
python live_test.py              # 全链路实机：后台跑 mvp --no-ui，前台用耳机播放测试音频
```

守护启动：`start-exam.bat` 默认就带守护（`plain` 只跑一次，`guard` 强制守护），
等价于 `python guardian.py`：拉起 `mvp.py`，崩溃按 1.5/3/5s 退避重启（首次 0.5s），
`GUARDIAN_MAX` 限制重启次数（0=不限），日志写 `guardian.log`，重启事件同时写 `run.log`。
窗口位置/大小存在 `ui_state.json`（10s 一次 + 退出时），自愈后自动恢复。

## 和商业版的差距（按实现成本排序）

1. **流式 ASR**：本 MVP 是「分块伪流式」（每 1.2s 重转一次整段）；商业版用 WebSocket 真流式（阿里 paraformer-realtime / 火山 / whisper-streaming），能到 300ms 出字。
2. **问题检测**：它把「是不是在问我」做成服务端模型（带 `is_me` 声纹判定），规则版在多人会议里会误触发。
3. **动作捕捉精度**：官网是自研模型（圆环进度、5s 托脸判定、多摄像头切换）；本机用 mediapipe 关键点 + 简单阈值，够用但抗光照差。
4. **DOM 适配器**：已做基础版（`dom.py`，CDP 优先 + UIA 兜底）；商业版为各平台写了选择器/交互适配（点击「运行」、读测试用例、贴回代码）。
5. **看护进程**：已做基础版（`guardian.py`，崩溃重启 + 退避）；商业版还监控防截屏状态、句柄失效重注入。
6. **伪装壳细化**：自定义图标、桌面预览未做；小窗已有三套样式（`THEME` + `Ctrl+Alt+Y`）。
