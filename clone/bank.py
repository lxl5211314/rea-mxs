"""本地题库：命中就原样用你写好的答案，不走 LLM。

文件：clone/题库.csv（或 BANK_CSV 指定的路径）
格式：第一列问题、第二列答案；CSV/TSV/Excel 导出的 csv 都认；带「序号」列会自动跳过。
匹配：先归一化精确匹配，再相似度匹配（默认 0.86，够近才用）。
"""
from __future__ import annotations

import csv
import difflib
import os
import re


def _norm(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\s，。！？、,.!?;；:：\"'“”‘’（）()\[\]【】…—\-]+", "", s)
    return s


def _read_rows(path: str) -> list[list[str]]:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            return [["" if c is None else str(c) for c in row]
                    for row in ws.iter_rows(values_only=True)]
        finally:
            wb.close()
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    sample = text[:4096]
    delim = "\t" if sample.count("\t") > sample.count(",") else ","
    return [row for row in csv.reader(text.splitlines(), delimiter=delim)]


def _core(s: str) -> str:
    """去掉口头填充词再比，避免「请简单做一下自我介绍吧」这种问法差 0.02 就漏掉。"""
    s = _norm(s)
    for w in ("请你", "请", "麻烦", "简单", "简短", "一下", "下", "吧", "呢", "啊", "嘛",
              "帮我", "我想", "先", "那么", "那", "您", "你"):
        s = s.replace(w, "")
    return s


class QuestionBank:
    def __init__(self, path: str | None = None, threshold: float = 0.86) -> None:
        self.items: list[tuple[str, str, str]] = []  # (原始问题, 归一化, 答案)
        self.threshold = float(os.getenv("BANK_THRESHOLD") or threshold)
        p = path or os.getenv("BANK_CSV") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "题库.csv")
        self.path = p
        self.load_error = ""
        if not os.path.exists(p):
            return
        try:
            rows = _read_rows(p)
        except Exception as e:
            self.load_error = f"{type(e).__name__}: {e}"
            return
        for row in rows:
            cells = [c.strip() for c in row]
            if len(cells) < 2:
                continue
            # 先去掉「序号」列，再判表头（表头可能写成 序号/问题/答案 三列）
            if re.fullmatch(r"\d+", cells[0]) and len(cells) >= 3:
                cells = cells[1:]
            head = [c.lower() for c in cells[:3]]
            if any(h in ("问题", "question", "题目", "题干") for h in head[:2]) \
                    or any(h in ("答案", "answer") for h in head):
                continue
            q, a = cells[0], cells[1]
            if not q or not a:
                continue
            self.items.append((q, _norm(q), a))

    def __len__(self) -> int:
        return len(self.items)

    def match(self, text: str) -> tuple[str, str] | None:
        """返回 (命中的问题, 答案)；没命中返回 None。"""
        if not self.items:
            return None
        t = _norm(text)
        if len(t) < 3:
            return None
        for q, nq, a in self.items:
            if t == nq:
                return q, a
        core_t = _core(text)
        best, best_r = None, 0.0
        for q, nq, a in self.items:
            # 长度差太大就别比了，避免短问题吃掉长问题
            if min(len(t), len(nq)) / max(len(t), len(nq)) < 0.6:
                continue
            core_q = _core(q)
            r = difflib.SequenceMatcher(None, core_t, core_q).ratio()
            if r > best_r:
                best, best_r = (q, a), r
        if best and best_r >= self.threshold:
            return best
        return None

    def summary(self) -> str:
        if self.load_error:
            return f"[bank] 题库读取失败: {self.load_error}"
        if not self.items:
            return f"[bank] 未加载题库（可选：在 {self.path} 放「问题,答案」两列表格）"
        return f"[bank] 已加载 {len(self.items)} 条：{self.path}"
