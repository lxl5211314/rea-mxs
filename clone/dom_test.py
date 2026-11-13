# -*- coding: utf-8 -*-
"""dom.py 自检：离线题干提取 + 本机浏览器实时读取（有浏览器才测）。"""
import io
import os

LOG = io.StringIO()


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    LOG.write(s + "\n")


import dom

SAMPLE = """牛客网
我的题库
题目列表
1. 两数之和
2. 链表反转
给定一个整数数组 nums 和一个目标值 target，请你在该数组中找出和为目标值的那两个整数，
并返回它们的数组下标。你可以假设每种输入只会对应一个答案。
示例 1：
输入：nums = [2,7,11,15], target = 9
输出：[0,1]
请用任意语言实现。
收藏
提交
运行
上一题
下一题
"""

q = dom.extract_question(SAMPLE)
log("OFFLINE_LEN", len(q))
log("OFFLINE_HEAD", q[:80].replace("\n", " / "))
assert "两数之和" in q or "nums" in q, q
assert "收藏" not in q and "提交" not in q
assert dom.looks_like_question(q) is True
assert dom.extract_question("登录\n注册\n首页") == ""

# 实时：本机是否有浏览器
win = dom.find_browser()
if win is None:
    log("LIVE skip: 没有检测到浏览器窗口")
else:
    log("LIVE window:", (win.Name or "")[:60], "|", win.ClassName)
    txt = dom.page_text(win)
    log("LIVE page_chars", len(txt))
    q2 = dom.read_question()
    log("LIVE question_chars", len(q2))
    log("LIVE question_head", q2[:100].replace("\n", " / "))

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dom_test.log"),
     "w", encoding="utf-8").write(LOG.getvalue())
print("DOM_TEST_OK", flush=True)
