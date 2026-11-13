"""笔试链路离线自检：造题图 → 视觉模型作答 → 校验题型标记/短答/签名。

两张图：
  1) 编程题（两数之和，带 class Solution 模板）
  2) 选择题（4 个选项）
不需要开关窗口，也不采集音频。
"""
import io
import os
import sys
import time

os.environ.setdefault("MODE", "exam")


class _Tee:
    """同时写控制台和 utf-8 日志（PowerShell 管道会按 GBK 解码，必须自己写文件）。"""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8", buffering=1)

    def write(self, s):
        self.f.write(s)
        try:
            sys.__stdout__.write(s)
        except Exception:
            pass

    def flush(self):
        self.f.flush()


sys.stdout = _Tee(os.path.join(os.path.dirname(os.path.abspath(__file__)), "exam_e2e.log"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import mvp  # noqa: E402
from shot import prepare  # noqa: E402

FONT = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22, index=0)


def make_image(lines, w=980, h=None):
    h = h or (24 + 34 * len(lines) + 24)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    y = 24
    for line in lines:
        d.text((24, y), line, fill="black", font=FONT)
        y += 34
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def run(name, lines):
    png = make_image(lines)
    prepped = prepare(png)
    brain = mvp.Brain(os.getenv("ROLE", "后端工程师"), "")
    t0 = time.time()
    first = []
    text = brain.answer_image(
        prepped,
        mvp._shot_prompt(),
        on_delta=lambda d: first.append(time.time()) or None,
    )
    cost = time.time() - t0
    kind = mvp._exam_kind(text)
    tidy = mvp._exam_tidy(text)
    print(f"\n[{name}] {len(png)//1024}KB → 规整 {len(prepped)//1024}KB｜"
          f"首字 {first[0]-t0:.2f}s / 总 {cost:.2f}s / {len(text)} 字", flush=True)
    print(f"[{name}] 题型={kind or '(无标记)'}｜签名={mvp._code_ok(text)}｜"
          f"短答后 {len(tidy)} 字", flush=True)
    print(text[:500], flush=True)
    if tidy != text:
        print("---- 选择题/判断题压短后 ----", flush=True)
        print(tidy, flush=True)
    return kind, text, tidy


code_img = [
    "1. 两数之和",
    "给定一个整数数组 nums 和一个整数目标值 target，请你在该数组中找出和为",
    "目标值 target 的两个整数，并返回它们的数组下标。",
    "",
    "class Solution:",
    "    def twoSum(self, nums: List[int], target: int) -> List[int]:",
]
choice_img = [
    "3. 下列关于 TCP 三次握手的说法，正确的是（  ）",
    "A. 第三次握手可以携带数据",
    "B. 第二次握手由客户端发起",
    "C. 三次握手的主要目的是同步序列号并确认双方收发能力",
    "D. 握手过程中不会消耗序列号",
]

k1, t1, _ = run("编程题", code_img)
k2, t2, tidy2 = run("选择题", choice_img)

ok = True
if k1 != "编程题":
    print(f"[e2e] 期望题型 编程题，实际 {k1!r}", flush=True)
    ok = False
if not mvp._code_ok(t1):
    print("[e2e] 编程题答案缺函数签名", flush=True)
    ok = False
if k2 != "选择题":
    print(f"[e2e] 期望题型 选择题，实际 {k2!r}", flush=True)
    ok = False
if len(tidy2) >= len(t2) and len(t2) > 90:
    print(f"[e2e] 选择题没有被压短：{len(t2)} → {len(tidy2)}", flush=True)
    ok = False
print("\n" + ("EXAM_E2E_OK" if ok else "EXAM_E2E_CHECK"), flush=True)
