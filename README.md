# aaa_msx — 面试侠逆向 + 自研替代品

把 `C:\Program Files\msx-client`（面试侠桌面端，Tauri v2 + WebView2）完整逆向后，用 Python 重写一个自己的版本。

## 目录

```
E:\aaa_msx\
├─ README.md                      本文件
├─ docs\
│  ├─ 面试侠逆向报告.md            12 节完整报告（架构/鉴权/API/ASR 协议/笔试 SSE/隐身三层/薄弱点）
│  ├─ 交接文档.md                  接手必读：现状/环境/坑/路线图/验收标准
│  ├─ 开发日志.md                  逐日记录（踩坑、基准数据、改动清单）
│  ├─ 操作步骤说明.md              从零到可用：安装/配置/自检/启动/热键/排错
│  ├─ 快捷键.md                    常用 10 个 + 全部热键速查（面试/笔试/窗口/退出）
│  ├─ 检测风险评估.md              牛客等平台能检测到什么、怎么规避
│  └─ 官网文档要点.md              2026-11 抓取的 mianshixia.cn 功能/设置/铁律（对齐基准）
├─ AGENTS.md                       AI 代理工作指南（约定、坑、文档同步规则）
├─ clone\                         ← 自研实现（现在主要在这里干活）
│  ├─ mvp.py                      主程序：loopback → VAD → ASR → 判定 → LLM 流式 → 防截屏浮窗
│  ├─ profile.py                  岗位/简历/知识库/提示词注入（本地解析 `资料\`）
│  ├─ shot.py                     整屏/窗口/框选/长截图（截图前自动隐藏浮窗）
│  ├─ bank.py                     题库 CSV 匹配
│  ├─ tts.py                      SAPI 语音播报
│  ├─ mobile.py                   手机局域网页（二维码 + 遥控）
│  ├─ hotkeys.py                  全局热键 + 鼠标手势
│  ├─ grid.py                     图形准备页：网格 + 涂鸦（Ctrl+Alt+G）
│  ├─ dom.py                      DOM 读题：CDP（9223）优先 + UIA 兜底
│  ├─ guardian.py                 看护进程：崩溃自动重启（guardian.log）
│  ├─ selftest.py                 逐层自检：deps / capture / asr / e2e / llm
│  ├─ features_test.py            题库 + 视觉 + 手机 联调
│  ├─ live_test.py                无界面全链路（写 live.log）
│  ├─ bench_asr.py / bench_llm2.py / devices.py / setvol.py / wda_test.py
│  ├─ .env / .env.example / requirements.txt / 题库.csv
│  └─ README.md
├─ models\                        faster-whisper-tiny / -base（离线）
└─ reverse\                       ← 逆向素材（只读参考）
   ├─ bundle_pretty.js            前端 bundle 美化版，36,684 行，行号索引都基于它
   ├─ bundle_strings.txt          16,641 条字符串字面量
   ├─ api_list.txt                36 条后端接口
   ├─ msx_ascii.txt               exe 的 157,198 条 ASCII 串（含全部 Tauri 命令名/原生模块字符串）
   ├─ assets\                     369 个 brotli 解压后的前端资源（index.html + assets\）
   └─ scripts\                    逆向期间用过的脚本
```

## 逆向结论（一句话版）

客户端只是壳：**答案生成、题目检测、计时扣费、声纹全在服务端**。客户端拿得出手的只有三件事——系统音频回环采集、`SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` 防截屏、以及把窗口伪装成待办/备忘录。

- 鉴权：所有请求靠 query 里的 `?code=<激活码>`，无签名、无 token（`bundle_pretty.js:9408`）。
- 面试：`wss://backend.mianshixia.cn/ws/asr?data=<b64url>&channel=system`，握手只带 `user_id`（`:19582`）。
- 笔试：`POST backend.mianshixia.cn/api/writing` SSE，前端只上传截图 base64 和站点适配器抽到的正文（`:18810`）。
- 隐身：L1 `WDA_EXCLUDEFROMCAPTURE`；L2 `resources\msx-capture-guard.exe` 注入 `msx-capture-affinity.dll` 做「解保护→自截图→判 uniform_blank→重加保护」的看护；L3 伪装壳 + 点击穿透。

## 自研进度

| 模块 | 状态 |
|---|---|
| WASAPI loopback 采集（48k→16k） | 已完成，本机验证（耳机输出，peak RMS 0.19） |
| 能量 VAD 断句（partial/spec/final 三级） | 已完成 |
| faster-whisper 本地 ASR | 已完成（base@cuda 0.21s / 6.8s 音频） |
| 问题判定（疑问词 + 问号） | 已完成，待用真实面试录音调 |
| LLM 流式作答 + 简历/岗位注入 | 已完成（智能交付 relay，正文首字 0.90s） |
| 早触发（边说边识别、预断句抢跑） | 已完成，实机验证 |
| 置顶透明浮窗 + 防截屏 + 点击穿透 + 热键 | 已完成 |
| 伪装壳（标题 Settings + 任务栏/Alt-Tab 隐藏） | 已完成（自定义图标/多套样式未做） |
| 截图出答案（整屏/窗口/框选/长截图） | 已完成（视觉 flash 首字 1.4s） |
| 笔试模式（语言 + 力扣/ACM 提示词） | 已完成（首次启动弹准备页，18 种语言 + 两种代码模式） |
| 笔试题型分类（编程/问答/选择/判断/填空/图形推理） | 已完成（模型首行输出 `【题型】`，选择/判断题自动压到 2 行） |
| 编程题签名校验 + 缺签名重试 | 已完成（`_CODE_SIG_RE`；缺 `class`/`def` 带模板提示重试一次） |
| 长截图兜底 | 已完成（拼不上就两段分别识别；超时也先识别上半段） |
| 牛客等反检测加固 | 已完成（热键不下发、手势吞点击、框选不抢焦点、控制台 WDA、`EXAM_SAFE=1`） |
| 窗口形态 / 空闲快捷键卡片 | 已完成（默认常驻可见 + `EXAM_IDLE=1`；`EXAM_GHOST=1` 可切幽灵窗） |
| 窗口可读性 / 鼠标拖动缩放 | 已完成（自绘深色底板，左键拖动 + 右下角缩放 + `Ctrl+滚轮` 字号 + `Alt+滚轮` 透明度） |
| 答案/解析分色 + 截图崩溃修复 | 已完成（`【答案】` 青蓝高亮块、`【解析】` 灰蓝小字；截图隐身改走主线程，修掉 `0xC000041D`） |
| 本地题库原样命中 | 已完成（归一化 + difflib） |
| 回答风格（极简/标准/详细/大纲） | 已完成 |
| 手机联动 / 语音播报双机位 | 已完成，**手机默认关**（`MOBILE=0`）；需要时开 |
| 动作捕捉（扶眼镜/眨眼） | 已完成（mediapipe tasks + 本地 .task 模型，需开摄像头） |
| ⚡ 速答（一句话先上屏） | 已完成（实测 1.1s，完整回答首字 +0.15s） |
| 资料库（简历/知识库/提示词模板） | 已完成（`clone\资料\`，本地解析；岗位/简历/知识库/固定要求都进 system） |
| 回答档位（灵动/睿智）+ 翻译对照 | 已完成（`LLM_PROFILE`、`TRANSLATE=1`） |
| 题库 Excel（xlsx）+ 表头自动跳过 | 已完成（openpyxl；「序号」列自动剥掉） |
| 小窗样式预设（极暗/蓝灰/大字） | 已完成（`THEME`，`Ctrl+Alt+Y` 运行时切换） |
| 久采不到声音自动回退 | 已完成（8s 提示 / 20s 切默认输出，`AUDIO_FALLBACK=1`） |
| 截图识别回显（缩略图确认没截错） | 已完成（截到的原图缩略图贴进浮窗，240×100 内等比） |
| 图形准备页（网格+涂鸦） | 已完成（`Ctrl+Alt+G`：全屏网格+中线，左键画线/右键清空，不抢浏览器焦点） |
| DOM 读题（不截图，直接读页面文字） | 已完成（`Ctrl+Shift+D`：CDP `127.0.0.1:9223` 优先，UIA 兜底；`DOM_AUTO=1` 自动读题作答） |
| 追问预判 | 已完成（`Ctrl+Shift+U`：3 个最可能的追问 + 一句要点，追加在当前答案后） |
| 窗口移动（不吞方向键） | 已完成（`Shift+方向键` ±20px，`hotkeys.install` 对这四个组合 `suppress=False`） |
| 看护进程（崩溃自动重启） | 已完成（`guardian.py`，退避 1.5/3/5s，`GUARDIAN_MAX` 限次；`start-exam.bat guard`） |
| 真流式 ASR | 未做（现为分块伪流式） |

## 模型配置（当前实际在用）

| 环节 | 用什么 | 说明 |
|---|---|---|
| 答题 LLM | **智能交付 relay 的 `deepseek-v4.1-flash`** | base_url `http://127.0.0.1:19300/v1`，api_key `local-yonyou-relay`；`LLM_REASONING_EFFORT` 留空 + `LLM_EXTRA_JSON={"thinking":{"type":"disabled"}}` 关思考；`LLM_WARM=1` 保活，实测正文首字 0.83–1.45s |
| 视觉（截图答题） | `deepseek-v4.1-flash`（关思考） | 实测首字 1.42s / 总 3.35s，题干识别准确；GLM-5.3 波动大（1.5–4.7s）故不用作默认 |
| ASR | **本地 `faster-whisper-base` @ CUDA** | relay 没有 `/v1/audio/transcriptions`（404），语音识别只能本地；显卡 6G 下 6.8s 音频 0.21s |

「智能交付」就是 opencode 里配的 `yonyou` provider，**必须先把 opencode 开着**（relay 是它起的本地服务）。
没有 opencode 时改 `.env` 用直连 DeepSeek（`.env.example` 的 B 段，模型名 `deepseek-flash`，但延迟会更差）。

## 启动（Windows，双击 bat）

**日常两个入口，双击即可**（和官网一致：一个客户端，面试听声音、笔试看截图）：
| 双击 | 场景 | 链路 |
|---|---|---|
| `E:\aaa_msx\start.bat` | 面试模式 | 系统音频 loopback → VAD → ASR → 问题判定 → 作答（约 20s 就绪，要加载 ASR） |
| `E:\aaa_msx\start-exam.bat` | 笔试模式 | **只截图** → 视觉模型 → 答案；**不采集音频、不加载 ASR**（约 3s 就绪）。默认带守护：崩溃 0.5s 自愈，窗口位置/大小自动恢复 |
| `E:\aaa_msx\start-exam-compat.bat` | 笔试兜底 | 同上，关掉 5 秒隐身保活与控制台处理；个别机器上仍有兼容问题时用它 |
| `E:\aaa_msx\stop-exam.bat` | 关闭全部 | 结束 mvp + guardian + 宿主 cmd（控制台隐藏后也能关）；桌面快捷方式「关闭msx-clone」 |

> 崩溃取证：`clone\run.log` 记录每一步（时间 + pid）；bat 退出码非 0 时自动打印最后 12 行，先看它再判断。
> 自愈：`start-exam.bat` 默认走 `guardian.py`，中途崩了约 1 秒自动回来；`start-exam.bat plain` 只跑一次（调试用）。
> 整屏共享：控制台默认隐藏（`CONSOLE_HIDE=1`）、托盘默认不建（`TRAY=0`），桌面上只剩被 WDA 剔除的浮窗。
> 窗口被隐藏了：按 `F8`（或 `Ctrl+Shift+B` / `Ctrl+Alt+S`）；实在找不到就再双击一次 `start-exam.bat`，它会把已经在跑的那个窗口弹出来。

> 第一次跑 `start-exam.bat` 会先弹语言/代码模式准备页（18 种语言、力扣/ACM）；以后想改，
> 命令行走 `start-exam.bat setup`（或直接 `python clone\exam_setup.py`）。
> 自检不是日常入口：`python clone\selftest.py deps|e2e|llm`；无界面：`python clone\mvp.py --no-ui`。
> 等价的脚本也在 `E:\aaa_msx\clone\` 下（`clone\start.bat` / `clone\start-exam.bat`），根目录这两个只做转发。

笔试模式用法：`Shift+双击` 整屏 / `Alt+双击` 鼠标所在窗口 / `Ctrl+Shift+S` 拖框只截题干 / `Shift+Alt+双击` 两次长截图；
`Ctrl+Shift+X` 取消当前截图，已出的部分答案保留；`Ctrl+Shift+G` 重新识别当前截图（不用重截）；`Ctrl+Shift+R` 重新截一张；`Ctrl+Shift+L` 题目列表。
`Ctrl+Shift+D` 直接从页面读题（DOM，不截图，需调试端口的浏览器）；`Ctrl+Shift+U` 追问预判；`Shift+方向键` 移动窗口。
要做牛客/力扣类页面读题：用 `python clone\dom.py` 里的 `open_debug_browser()` 拉起带 `--remote-debugging-port=9223` 的 Chrome/Edge，
登录后打开题目页，再按 `Ctrl+Shift+D`；确认读得对再开 `DOM_AUTO=1` 自动作答。浮窗里只出答案，不出音频相关状态。
截图前浮窗自动透明，图里不会出现自己；框选层不抢焦点，浏览器不会因此判切屏；连拍两张至少隔 1 秒。
更隐蔽可设 `EXAM_SAFE=1`：关摄像头/手机端口/语音，窗口默认隐藏 + 点击穿透，`F8` 显示。

**窗口形态（默认常驻可见）**：`EXAM_GHOST=0` + `EXAM_IDLE=1`。没截图时窗口显示快捷键卡片，截图瞬间自动隐身、抓完恢复，图里不会出现自己；窗口不会自动消失，退出按 `Ctrl+Shift+Q` 连按两次。
共享/录屏里对方看不到这个窗口：WDA `0x11` 在本机 Win11 上对 WGC/DXGI **和 GDI BitBlt** 都实测生效（`clone/gdi_alpha_test.py` 的 on/off 对照）。
想更隐蔽可改 `EXAM_GHOST=1`：启动隐藏，答案到达才出现，`GHOST_HIDE_AFTER=10` 秒后自动隐藏，`F8` 随时叫出。

bat 都做了：`chcp 65001` → 切到脚本目录 → `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` →
找不到 `python` 回退 `E:\python3.10.4\python.exe` → `.env` 缺失自动复制 → 跑完 `pause`。
`start.bat` 设 `MODE=interview`、`start-exam.bat` 设 `MODE=exam`，**bat 里的 MODE 优先于 `.env`**。

手机联动默认关闭（`MOBILE=0`，终端不再出二维码），需要第二机位时再改。

> bat 文件必须是 **ASCII + CRLF**：cmd.exe 会按 GBK 解析 UTF-8 批处理，中文注释会让整行错位报
> `'保活' 不是内部或外部命令`；LF-only 换行也会让 `rem`/括号块解析错乱。改 bat 请保持纯英文。

手动跑（等价）：

```powershell
Set-Location E:\aaa_msx\clone
python selftest.py deps                     # 依赖 + 音频设备 + LLM 端点
python selftest.py e2e -w "C:\Program Files\msx-client\resources\self-test-interviewer.wav"
python selftest.py llm                      # 测首字延迟
python live_test.py                         # 播放测试音频，全链路（写 live.log）
python mvp.py                               # 真跑：浮窗 + 热键 + 手机二维码
python guardian.py                          # 看护启动：崩溃自动重启（日志 guardian.log）
```

热键：`F8` 显隐 / `F9` 点击穿透 / `F10` 透明度 / `Ctrl+Alt+Y` 切样式 / `Ctrl+Alt+G` 图形准备页（网格+涂鸦）/ `Ctrl+Shift+D` DOM 读题 / `Ctrl+Shift+U` 追问预判 / `Ctrl+Shift+G` 笔试=重识别当前截图 / `Ctrl+Shift+R` 重答上一题 / `Ctrl+Shift+L` 题目列表 / `Shift+方向键` 移动窗口 / `Ctrl+Shift+X` 取消 / `Ctrl+Shift+H` 说明 / `Ctrl+Shift+Q` 连按两次退出。
截图：`Shift+双击` 整屏 / `Alt+双击` 窗口 / `Ctrl+Shift+S` 框选 / `Shift+Alt+双击` 长截图。
反检测：热键默认吞掉不下发（`HOTKEY_SUPPRESS=1`）、手势触发吞点击、控制台窗口也设 `WDA_EXCLUDEFROMCAPTURE`（`CLOAK_CONSOLE=1`）。

## 设置中心（官网九栏 → 本地实现）

| 官网设置 | 本地怎么配 | 状态 |
|---|---|---|
| 通用（目标岗位） | `ROLE=后端工程师，5 年经验…` | ✅ |
| 基础配置（回答风格） | `ANSWER_STYLE=brief\|standard\|detailed\|outline` | ✅ |
| 模型（灵动/睿智） | `LLM_PROFILE=speed\|natural` | ✅ |
| 简历（1 份，PDF/Word/MD ≤3MB） | `clone\资料\简历.*` | ✅ 本地解析 |
| 知识库（≤2 份，≤3MB） | `clone\资料\知识库\*.md\|pdf\|docx` | ✅ 本地解析 |
| 题库（问题,答案 ≤3MB/500 条） | `clone\题库.csv` / `.xlsx` / `BANK_CSV` | ✅ 自动跳表头 |
| 提示词模板（每类 5 条、启用 1 条、≤2000 字） | `clone\资料\提示词_面试.txt` / `提示词_笔试.txt` | ✅ 单条启用 |
| 语音播报（笔试第二机位） | `TTS=1` + `TTS_VOICE` | ✅ |
| 眼神纠正（NVIDIA Broadcast） | 官网 Windows 也是调 NVIDIA Broadcast「目光接触」，本地不重复实现 | ⚠️ 用 NVIDIA 官方 |

> 官网 `/docs/before` 四条铁律同样适用：先开会议软件再开本工具；全程不切音频设备；
> 网页端只共享窗口；正式前 10 分钟跑一次 `python clone\selftest.py deps` + 一次 `e2e`。

## 三天计划

1. **D1 可用性**：~~把「问题→答案」首字压到 1.5s 内~~ **已达成 0.90s**（早触发 + 关思考 + 保活）；真实会议录音调 VAD 阈值、换真流式 ASR 仍是 D1 剩余项。
2. **D2 交互**：~~快捷键全套 / 答案历史 / 截图出答案 / 题库 / 手机页~~ **已完成**；剩余多轮追问上下文、token 用量与延迟显示。
3. **D3 稳妥**：断线重连、ASR 服务商可切换（本地 whisper / 云端 API）、单文件打包（PyInstaller）。
