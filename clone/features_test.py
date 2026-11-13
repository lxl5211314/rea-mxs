"""功能自检：题库 / 截图+视觉 / 语音播报 / 手机联动。不依赖麦克风，不需要开会议软件。"""
import io
import json
import os
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mvp  # noqa: E402  同时负责加载 .env

LOG = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "features.log"),
              "w", encoding="utf-8")


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


# ---------------- 1. 题库
from bank import QuestionBank  # noqa: E402

bank = QuestionBank()
log("[bank]", bank.summary())
for q in ["请做一下自我介绍", "请简单做一下自我介绍吧", "今天天气怎么样"]:
    hit = bank.match(q)
    log("  ", q, "→", ("命中：" + hit[0]) if hit else "未命中")

# ---------------- 2. 截图 + 视觉模型
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

img = Image.new("RGB", (900, 300), "white")
d = ImageDraw.Draw(img)
fp = r"C:\Windows\Fonts\msyh.ttc"
font = ImageFont.truetype(fp, 26) if os.path.exists(fp) else ImageFont.load_default()
d.text((30, 30), "请用 Python 实现：给定数组 nums 和整数 target，", font=font, fill="black")
d.text((30, 80), "返回和为 target 的两个元素的下标，要求 O(n)。", font=font, fill="black")
d.text((30, 150), "示例：nums = [2,7,11,15], target = 9  →  [0,1]", font=font, fill="black")
buf = io.BytesIO()
img.save(buf, format="PNG")
png = buf.getvalue()
log("[shot] 测试图", len(png), "B")

brain = mvp.Brain(os.getenv("ROLE", "后端工程师"), os.getenv("RESUME", ""))
if brain.client is None:
    log("[vision] 无 key，跳过")
else:
    t0 = time.time()
    acc = []
    try:
        text = brain.answer_image(png, "下面这张图里有什么题目？把题目原文抄出来，然后给代码答案。",
                                  lambda p: acc.append(p))
        log(f"[vision] {mvp.VISION_MODEL} {time.time()-t0:.2f}s {len(text)} 字")
        log(text[:600])
    except Exception as e:
        log("[vision] 失败", type(e).__name__, e)

# ---------------- 3. 语音播报（不真的出声也行）
if os.getenv("TTS_TEST", "0") not in ("0", "false", "False"):
    from tts import Speaker  # noqa: E402

    sp = Speaker(enabled=True)
    sp.start()
    sp.speak("这是一条语音播报测试，订单中心重构把 QPS 从八百提到六千。")
    time.sleep(4)
    sp.stop()
    log("[tts] error =", sp.error or "(none)")

# ---------------- 4. 手机联动
if os.getenv("MOBILE", "1") not in ("0", "false", "False"):
    from mobile import MobilePad, lan_ip  # noqa: E402

    cmds = []
    pad = MobilePad(lambda c: cmds.append(c), port=int(os.getenv("MOBILE_PORT", "8765")))
    pad.start()
    time.sleep(0.6)
    pad.update(question="请做一下自我介绍", answer="我是做后端开发的……", status="已识别问题")
    url = f"http://{lan_ip()}:{pad.port}/?t={pad.token}"
    api = f"http://{lan_ip()}:{pad.port}"
    log("[mobile]", url)
    try:
        html = urllib.request.urlopen(url, timeout=3).read().decode("utf-8", "ignore")
        log("[mobile] 页面", len(html), "B，含答案卡：", "我是做后端开发" in html)
        j = json.loads(urllib.request.urlopen(f"{api}/api/state?t={pad.token}", timeout=3).read().decode())
        log("[mobile] state", str(j)[:200])
        req = urllib.request.Request(f"{api}/api/cmd?t={pad.token}", data=b'{"cmd":"next"}',
                                     headers={"Content-Type": "application/json"})
        log("[mobile] cmd resp", urllib.request.urlopen(req, timeout=3).read().decode())
        time.sleep(0.3)
        log("[mobile] 收到指令", cmds)
    except Exception as e:
        log("[mobile] 失败", type(e).__name__, e)
    pad.stop()

log("FEATURES_DONE")
