"""资料目录：简历 / 知识库 / 提示词模板，按官网的能力组织成「设置中心」。

目录（默认 clone/资料，可用 MSX_PROFILE_DIR 改）：
    资料/简历.pdf|docx|md|txt      1 份，≤3MB
    资料/知识库/*.pdf|docx|md|txt  最多 2 份，每份 ≤3MB
    资料/提示词_面试.txt           ≤2000 字，追加到面试 system prompt 后面
    资料/提示词_笔试.txt           ≤2000 字，追加到笔试 system prompt 后面

只做本地解析，不联网、不上传；读不到就静默跳过，不影响启动。
"""
from __future__ import annotations

import os
import unicodedata

MAX_BYTES = 3 * 1024 * 1024
RESUME_LIMIT = 4000
KNOW_LIMIT = 2500
KNOW_MAX = 2
PROMPT_LIMIT = 2000
EXTS = (".pdf", ".docx", ".doc", ".md", ".markdown", ".txt")


def _extract(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(path)
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        if ext == ".docx":
            import docx

            d = docx.Document(path)
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for row in t.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            return "\n".join(parts)
        if ext in (".md", ".markdown", ".txt"):
            raw = open(path, "rb").read()
            for enc in ("utf-8-sig", "utf-8", "gb18030"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "ignore")
        # .doc（老二进制）/ 其他：python-docx 读不了，明确跳过
        return ""
    except Exception as e:
        print(f"[profile] 解析失败 {os.path.basename(path)}: {type(e).__name__}: {e}", flush=True)
        return ""


_RADICAL_FIX = str.maketrans({
    "⻰": "龙", "⻚": "页", "⻔": "门", "⻓": "长", "⻅": "见", "⻋": "车",
    "⻢": "马", "⻜": "飞", "⻛": "风", "⻥": "鱼", "⻦": "鸟", "⻨": "麦",
    "⸺": "—", "⸻": "—", "⼀": "一", "⼆": "二", "⼈": "人", "⼒": "力",
})


def _clean(text: str) -> str:
    # PDF 内嵌字体常把汉字映射成「康熙部首/兼容表意字」（如 ⼩/⼯），NFKC 归一成正常汉字；
    # 有些导出工具还会夹零字节，一并去掉，否则喂给模型会读到乱码。
    text = unicodedata.normalize("NFKC", text.replace("\x00", ""))
    # NFKC 管不到「CJK 部首补充」里那几个没有分解式的字，补一张小映射表
    text = text.translate(_RADICAL_FIX)
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank:
                out.append("")
            blank = True
            continue
        blank = False
        out.append(ln)
    return "\n".join(out).strip()


class Profile:
    def __init__(self, root: str | None = None) -> None:
        self.root = root or os.getenv("MSX_PROFILE_DIR") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "资料")
        self.resume = ""
        self.resume_src = ""
        self.knowledge: list[tuple[str, str]] = []  # (文件名, 正文)
        self.errors: list[str] = []
        self._load()

    # ---- 读取
    def _load(self) -> None:
        if not os.path.isdir(self.root):
            return
        # 简历：取第一份合法文件（重传即替换，和官网一致）
        for name in sorted(os.listdir(self.root)):
            p = os.path.join(self.root, name)
            if not os.path.isfile(p) or os.path.splitext(name)[1].lower() not in EXTS:
                continue
            if not name.startswith("简历") and "resume" not in name.lower():
                continue
            if os.path.getsize(p) > MAX_BYTES:
                self.errors.append(f"{name} 超过 3MB，已跳过")
                continue
            text = _clean(_extract(p))
            if text:
                self.resume = text[:RESUME_LIMIT]
                self.resume_src = name
                break
            if os.path.splitext(name)[1].lower() == ".doc":
                self.errors.append(f"{name} 是旧版 .doc，请另存为 .docx 或 PDF")

        kdir = os.path.join(self.root, "知识库")
        if os.path.isdir(kdir):
            for name in sorted(os.listdir(kdir)):
                if len(self.knowledge) >= KNOW_MAX:
                    break
                p = os.path.join(kdir, name)
                if not os.path.isfile(p) or os.path.splitext(name)[1].lower() not in EXTS:
                    continue
                if os.path.getsize(p) > MAX_BYTES:
                    self.errors.append(f"知识库/{name} 超过 3MB，已跳过")
                    continue
                text = _clean(_extract(p))
                if text:
                    self.knowledge.append((name, text[:KNOW_LIMIT]))

    # ---- 给 prompt 用
    def resume_text(self, fallback: str = "") -> str:
        return self.resume or fallback

    def context_block(self) -> str:
        if not self.knowledge:
            return ""
        chunks = [f"【{name}】\n{body}" for name, body in self.knowledge]
        return "参考资料（只在相关时引用，不要编造）：\n" + "\n\n".join(chunks)

    def prompt_addon(self, mode: str) -> str:
        name = "提示词_笔试.txt" if mode == "exam" else "提示词_面试.txt"
        env = "PROMPT_EXAM" if mode == "exam" else "PROMPT_INTERVIEW"
        text = os.getenv(env, "").strip()
        if not text:
            p = os.path.join(self.root, name)
            if os.path.exists(p):
                text = _clean(_extract(p))
        text = text[:PROMPT_LIMIT].strip()
        if not text:
            return ""
        return "\n\n【用户固定要求，必须遵守】\n" + text

    def summary(self) -> str:
        parts = []
        if self.resume:
            parts.append(f"简历 {self.resume_src or 'env'} {len(self.resume)} 字")
        if self.knowledge:
            parts.append("知识库 " + "、".join(f"{n}({len(b)}字)" for n, b in self.knowledge))
        return f"[profile] {self.root}：" + ("；".join(parts) if parts else "无资料（可选）")
