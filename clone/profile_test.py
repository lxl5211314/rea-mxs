"""资料目录 / 提示词模板 / xlsx 题库 离线自检（不联网）。

用法：python profile_test.py
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("OPENAI_API_KEY", "")  # 只验 prompt 拼装，不需要真 key

import mvp
from bank import QuestionBank
from profile import Profile

LINES: list[str] = []


def log(*a) -> None:
    s = " ".join(str(x) for x in a)
    LINES.append(s)
    print(s, flush=True)


def main() -> int:
    root = tempfile.mkdtemp(prefix="msx_profile_")
    with open(os.path.join(root, "简历.md"), "w", encoding="utf-8") as f:
        f.write("# 简历\n\n5 年 Java 后端，主导订单中心重构，QPS 800→6000。\n")
    kdir = os.path.join(root, "知识库")
    os.makedirs(kdir)
    with open(os.path.join(kdir, "JD.md"), "w", encoding="utf-8") as f:
        f.write("岗位要求：熟悉 Spring Cloud、分库分表、消息队列。\n")
    with open(os.path.join(root, "提示词_面试.txt"), "w", encoding="utf-8") as f:
        f.write("先一句话结论，再补 2 个要点。不要编造简历里没有的经历。\n")

    p = Profile(root)
    log(p.summary())
    log("resume_len", len(p.resume_text("fallback")))
    log("context_len", len(p.context_block()))
    log("addon", repr(p.prompt_addon("interview")))

    b = mvp.Brain("Java 后端工程师", p.resume_text(), context=p.context_block(),
                  addon=p.prompt_addon("interview"))
    log("system_has_resume", "订单中心重构" in b.system)
    log("system_has_jd", "分库分表" in b.system)
    log("system_has_addon", "不要编造" in b.system)
    log("system_has_translate", "中文对照" in b.system)
    assert b.system.count("{") == 0, "system prompt 还有未渲染的槽位"

    # xlsx 题库
    import openpyxl

    xp = os.path.join(root, "题库.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["序号", "问题", "答案"])
    ws.append([1, "请做一下自我介绍", "我是后端工程师，五年经验。"])
    ws.append([2, "你最大的缺点是什么", "有时过于追求细节，后来用时间盒约束。"])
    wb.save(xp)
    bank = QuestionBank(xp)
    log(bank.summary())
    hit = bank.match("麻烦你先自我介绍一下")
    log("bank_hit", hit[0] if hit else None)
    assert hit and "后端工程师" in hit[1]

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile_test.log")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(LINES) + "\n")
    log("OK ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
