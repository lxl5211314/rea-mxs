# -*- coding: utf-8 -*-
import io

add = """
### 32.7 逻辑自检与冒烟
- `exam_logic_test.py`（假 Brain，不联网）：选择题/判断题正文压到 2 行、题型解析、缺签名触发重试（calls=2 且采用第二版）、
  有签名不重试（calls=1）、未识别不重试 —— 全部 `[OK]`，输出 `EXAM_LOGIC_OK`。
- 踩到一个真 bug：模型现在第一行是「【题型】未识别」，旧的 `_looks_unrecognized()` 只看开头，守卫失效。
  已改为先剥 `【题型】…` 标记再判断。
- 冒烟：`MODE=exam` GUI 14s `ALIVE=True`、`ERR_BYTES=0`，热键含 `ctrl+shift+r/s`；
  `MODE=interview` GUI 14s `ALIVE=True`，stderr 只有 soundcard `data discontinuity`（无害），
  `[audio] 扬声器 (Realtek(R) Audio) 原本静音，已解除`（本机默认输出又切回扬声器）。
"""
p = r"E:\aaa_msx\docs\开发日志.md"
t = io.open(p, encoding="utf-8").read()
if "### 32.7" not in t:
    io.open(p, "a", encoding="utf-8").write(add)
    print("APPENDED")
else:
    print("ALREADY")
