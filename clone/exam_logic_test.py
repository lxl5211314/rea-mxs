"""离线校验笔试后处理：题型分流 / 选择题短答 / 编程题签名重试（不调网络）。"""
import os

os.environ.setdefault("MODE", "exam")

import mvp


class FakeBrain:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def answer_image(self, png, prompt, on_delta, cancel=None):
        self.calls.append(prompt)
        text = self.answers.pop(0)
        for ch in text:
            on_delta(ch)
        return text


def check(name, cond, extra=""):
    print(("[OK] " if cond else "[FAIL] ") + name + ((" " + extra) if extra else ""))
    return cond


ok = True
# 1) 选择题压短（题型标记 + 最多 2 行正文）
choice = ("【题型】选择题\n答案：C\n依据：三次握手同步序列号。\n"
          "A 不对，因为……\nB 不对，因为……\nD 不对，因为……")
body_lines = mvp._exam_tidy(choice).splitlines()[1:]
ok &= check("选择题正文压到 2 行", len(body_lines) == 2, repr(body_lines))
ok &= check("选择题总长受控", len(mvp._exam_tidy(choice)) <= 140)
ok &= check("题型解析", mvp._exam_kind(choice) == "选择题")

# 2) 编程题缺签名 -> 重试一次并采用第二版
fb = FakeBrain([
    "【题型】编程题\n思路：用哈希表遍历一遍。",
    "【题型】编程题\n思路：哈希表。\n```python\nclass Solution:\n    def twoSum(self, nums, target):\n        return []\n```",
])
out = mvp._exam_vision(fb, b"fake", "P", lambda s: None, on_retry=lambda: None)
ok &= check("缺签名触发重试", len(fb.calls) == 2, f"calls={len(fb.calls)}")
ok &= check("采用重试结果", "class Solution" in out)
ok &= check("重试提示生效", "照抄截图里的代码模板" in fb.calls[1])

# 3) 有签名 -> 不重试
fb2 = FakeBrain(["【题型】编程题\n```python\ndef f(x):\n    return x\n```"])
mvp._exam_vision(fb2, b"fake", "P", lambda s: None)
ok &= check("有签名不重试", len(fb2.calls) == 1, f"calls={len(fb2.calls)}")

# 4) 未识别 -> 不重试、原样返回
fb3 = FakeBrain(["【题型】未识别\n未识别到题目（看到的是：桌面），请重新框选题目区域"])
out3 = mvp._exam_vision(fb3, b"fake", "P", lambda s: None)
ok &= check("未识别不重试", len(fb3.calls) == 1)
ok &= check("未识别判定", mvp._looks_unrecognized(out3))

# 5) 判断题压短
judge = "【题型】判断题\n答案：错\n依据：三次握手不是四次。\n补充一大段无关分析"
ok &= check("判断题正文压到 2 行", len(mvp._exam_tidy(judge).splitlines()[1:]) == 2)

print("\n" + ("EXAM_LOGIC_OK" if ok else "EXAM_LOGIC_FAIL"))
