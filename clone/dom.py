# -*- coding: utf-8 -*-
"""从浏览器页面读题。两条路，优先 CDP（真 DOM），退 UIA（可访问性树）。

1) CDP：给 Chrome/Edge 加 `--remote-debugging-port` 启动一次（独立 profile，登录态会保留），
   之后 `Runtime.evaluate` 直接读 `document.body.innerText`，100% 是页面原文，不受缩放/遮挡影响。
   `DOM_CDP=http://127.0.0.1:9223`，`python -c "import dom; dom.open_debug_browser()"` 可拉起。
2) UIA：不装扩展、不开端口，读窗口的可访问性树；Chrome 只在检测到辅助技术时才暴露页面文本，
   所以命中率低于 CDP，作为兜底。

只读：不注入脚本、不改页面、不发业务请求。
"""
import json
import os
import re
import shutil
import subprocess
import time

KEYWORDS = ("nowcoder", "牛客", "leetcode", "力扣", "showmebug", "oxcoder",
            "hackerrank", "coderpad", "赛码", "acmcoder", "笔试", "考试", "在线编程")

HOST_HINTS = ("nowcoder.com", "leetcode.cn", "leetcode.com", "showmebug.com",
              "oxcoder.com", "hackerrank.com", "coderpad.io", "acmcoder.com")

NOISE = {
    "登录", "注册", "退出", "交卷", "提交", "运行", "调试", "保存", "下一题", "上一题",
    "上一页", "下一页", "收藏", "帮助", "题目列表", "我的", "首页", "通知", "设置",
    "开始考试", "确认", "取消", "返回", "全部", "通过率", "难度", "中等", "简单", "困难",
}

_QUESTION_HINT = re.compile(r"(？|\?|请|给定|以下|实现|设计|描述|简述|说明|计算|判断|选择|"
                            r"输入|输出|示例|要求|为什么|如何|什么是|谈谈)")

# 各平台题干容器（命中就用 innerText，比整页干净）
_JS = r"""
(() => {
  const sels = [
    '.question-content', '.subject-question', '.question-main', '.nc-post-content',
    '[data-track-load="description_content"]', '.challenge-body-html', '.problem-statement',
    '.question-title', '.problem-desc', '#question-content', '[class*="question-desc"]',
    '[class*="problem-content"]', 'article', 'main'
  ];
  for (const s of sels) {
    try {
      const el = document.querySelector(s);
      if (el && el.innerText && el.innerText.trim().length > 20) return el.innerText.trim();
    } catch (e) {}
  }
  return document.body ? document.body.innerText : '';
})()
"""

CDP_DEFAULT = os.getenv("DOM_CDP", "http://127.0.0.1:9223")
PROFILE = os.getenv("DOM_PROFILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "browser-data")


# ------------------------------------------------------------------ CDP
def cdp_pages(base: str | None = None, timeout: float = 2.0) -> list[dict]:
    import urllib.request

    base = (base or CDP_DEFAULT).rstrip("/")
    try:
        with urllib.request.urlopen(base + "/json", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return [p for p in data if p.get("type") == "page"]
    except Exception:
        return []


def _pick_page(pages: list[dict]) -> dict | None:
    if not pages:
        return None
    for p in pages:
        url = (p.get("url") or "").lower()
        if any(h in url for h in HOST_HINTS):
            return p
    for p in pages:
        url = (p.get("url") or "").lower()
        if url.startswith(("http://", "https://", "file://")):
            return p
    return pages[0]


def cdp_text(base: str | None = None, timeout: float = 2.5) -> str:
    """通过 CDP 读当前笔试页面的可见文本；失败返回 ""。"""
    page = _pick_page(cdp_pages(base, timeout))
    if not page:
        return ""
    try:
        from websockets.sync.client import connect
    except Exception:
        return ""
    try:
        with connect(page["webSocketDebuggerUrl"], open_timeout=timeout,
                     close_timeout=1, max_size=8 * 1024 * 1024) as ws:
            ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                "params": {"expression": _JS, "returnByValue": True,
                                           "awaitPromise": False}}))
            deadline = time.time() + timeout
            while time.time() < deadline:
                msg = json.loads(ws.recv(timeout=max(0.1, deadline - time.time())))
                if msg.get("id") == 1:
                    val = (msg.get("result", {}).get("result", {}) or {}).get("value")
                    return (val or "").strip()
    except Exception:
        return ""
    return ""


def cdp_alive(base: str | None = None) -> bool:
    return bool(cdp_pages(base, 1.0))


def open_debug_browser(url: str = "", base: str | None = None) -> bool:
    """用独立 profile + 调试端口拉起 Chrome（登录态保存在 clone\\browser-data）。

    已经活着就直接复用；返回是否可用。
    """
    if cdp_alive(base):
        return True
    base = (base or CDP_DEFAULT).rstrip("/")
    port = base.rsplit(":", 1)[-1]
    exe = (shutil.which("chrome") or shutil.which("chrome.exe")
           or shutil.which("msedge") or shutil.which("msedge.exe"))
    if not exe:
        for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            if os.path.exists(p):
                exe = p
                break
    if not exe:
        return False
    args = [exe, f"--remote-debugging-port={port}", f"--user-data-dir={PROFILE}",
            "--no-first-run", "--no-default-browser-check",
            "--force-renderer-accessibility"]
    if url:
        args.append(url)
    subprocess.Popen(args, close_fds=True)
    for _ in range(20):
        time.sleep(0.4)
        if cdp_alive(base):
            return True
    return False


# ------------------------------------------------------------------ UIA 兜底
def _top(control):
    try:
        return control.GetTopLevelControl()
    except Exception:
        return control


def find_browser(keywords=KEYWORDS):
    """返回笔试页面窗口（优先标题命中平台关键词），找不到返回 None。"""
    try:
        import uiautomation as auto
    except Exception:
        return None
    kw = [k.lower() for k in keywords]
    best, best_score = None, -1
    try:
        wins = list(auto.GetRootControl().GetChildren())
    except Exception:
        wins = []
    for w in wins:
        try:
            name = (w.Name or "").lower()
            cls = w.ClassName or ""
        except Exception:
            continue
        if not (cls in ("Chrome_WidgetWin_1", "MozillaWindowClass") or "Chrome" in cls):
            continue
        score = sum(1 for k in kw if k in name) * 10 + sum(1 for k in ("chrome", "edge", "浏览器") if k in name)
        if score > best_score:
            best, best_score = w, score
    if best is not None and best_score >= 10:
        return best
    try:
        fg = auto.GetForegroundControl()
        win = _top(fg) if fg else None
        if win is not None and _is_browser(win, keywords):
            return win
    except Exception:
        pass
    return best


def _is_browser(win, keywords) -> bool:
    try:
        cls = win.ClassName or ""
        name = win.Name or ""
    except Exception:
        return False
    if any(k in name.lower() for k in (k.lower() for k in keywords)):
        return True
    return cls in ("Chrome_WidgetWin_1", "MozillaWindowClass") or "Chrome" in cls


def page_text(win=None, max_chars: int = 20000) -> str:
    """UIA 兜底：优先 TextPattern，退化到遍历 Text/Edit 控件。"""
    try:
        import uiautomation as auto  # noqa: F401
    except Exception:
        return ""
    win = win or find_browser()
    if win is None:
        return ""
    try:
        doc = win.DocumentControl(searchDepth=30)
        if doc.Exists(1):
            tp = doc.GetTextPattern()
            if tp is not None:
                t = tp.DocumentRange.GetText(max_chars)
                if t and t.strip():
                    return t
    except Exception:
        pass
    out, seen, budget = [], set(), [6000]

    def walk(c, depth=0):
        if depth > 40 or budget[0] <= 0:
            return
        try:
            kids = c.GetChildren()
        except Exception:
            return
        for k in kids:
            budget[0] -= 1
            if budget[0] <= 0:
                return
            try:
                ct = k.ControlTypeName
                n = (k.Name or "").strip()
            except Exception:
                continue
            if ct in ("TextControl", "EditControl", "DocumentControl") and n and len(n) > 1:
                if n not in seen:
                    seen.add(n)
                    out.append(n)
            walk(k, depth + 1)

    walk(win)
    return "\n".join(out)[:max_chars]


# ------------------------------------------------------------------ 公共
def raw_text(prefer_cdp: bool = True) -> tuple[str, str]:
    """返回 (文本, 来源)，来源 = "cdp" / "uia" / ""。"""
    if prefer_cdp:
        t = cdp_text()
        if t:
            return t, "cdp"
    t = page_text()
    return (t, "uia") if t else ("", "")


def read_question(max_chars: int = 1500) -> str:
    t, _ = raw_text()
    return extract_question(t, max_chars=max_chars)


def read_question_ex(max_chars: int = 1500) -> tuple[str, str]:
    t, src = raw_text()
    return extract_question(t, max_chars=max_chars), src


def extract_question(text: str, max_chars: int = 1500) -> str:
    """从整页文本里挑题干——纯函数，便于离线测试。"""
    lines = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s or len(s) < 2:
            continue
        if s in NOISE:
            continue
        if len(s) <= 8 and not _QUESTION_HINT.search(s):
            continue
        lines.append(s)
    if not lines:
        return ""
    blocks, cur = [], []
    for s in lines:
        if s in NOISE or (len(s) <= 12 and s.endswith(("登录", "注册", "提交", "交卷"))):
            if cur:
                blocks.append(cur)
                cur = []
            continue
        cur.append(s)
    if cur:
        blocks.append(cur)

    def score(b):
        txt = "\n".join(b)
        return (len(_QUESTION_HINT.findall(txt)), len(txt))

    blocks.sort(key=score, reverse=True)
    q = "\n".join(blocks[0]) if blocks else "\n".join(lines)
    return q[:max_chars].strip()


def looks_like_question(text: str) -> bool:
    if not text or len(text) < 8:
        return False
    return bool(_QUESTION_HINT.search(text))
