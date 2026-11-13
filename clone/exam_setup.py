"""笔试准备页（命令行版）：选编程语言和代码模式，写回 .env。

官方桌面端是图形准备页；这里是零依赖的终端版，start-exam.bat 可以直接调。
    python exam_setup.py          # 交互选择
    python exam_setup.py 3 2      # 直接指定：第 3 种语言 + 第 2 种代码模式
"""
from __future__ import annotations

import os
import sys

LANGS = [
    "自动识别", "Java", "Python", "C++", "C", "C#", "Go", "JavaScript",
    "TypeScript", "Rust", "PHP", "Ruby", "Swift", "Kotlin", "Scala", "SQL",
    "Shell", "MATLAB", "R",
]
STYLES = ["力扣（只写核心函数）", "ACM（含输入输出完整程序）"]


def _env_path() -> str:
    return os.getenv("MSX_ENV") or os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _set_env(path: str, pairs: dict[str, str]) -> None:
    lines: list[str] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    seen = set()
    out = []
    for line in lines:
        m = line.split("=", 1)
        key = m[0].strip()
        if "=" in line and key in pairs and not key.startswith("#"):
            out.append(f"{key}={pairs[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, val in pairs.items():
        if key not in seen:
            out.append(f"{key}={val}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")


def _pick(title: str, items: list[str], default: int = 1) -> str:
    print(f"\n{title}")
    for i, it in enumerate(items, 1):
        mark = "*" if i == default else " "
        print(f" {mark}[{i}] {it}")
    try:
        raw = input(f"选择序号（回车={default}）：").strip()
    except EOFError:
        print()
        return items[default - 1]
    if not raw:
        return items[default - 1]
    try:
        n = int(raw)
        if 1 <= n <= len(items):
            return items[n - 1]
    except ValueError:
        pass
    print("输入无效，用默认。")
    return items[default - 1]


def main(argv: list[str]) -> int:
    if len(argv) >= 3:
        try:
            lang = LANGS[int(argv[1]) - 1]
            style = STYLES[int(argv[2]) - 1]
        except (ValueError, IndexError):
            print("参数应为：语言序号 模式序号")
            return 2
    else:
        lang = _pick("编程语言（截图里有模板时以模板为准）", LANGS, 1)
        style = _pick("代码模式", STYLES, 1)
    path = _env_path()
    _set_env(path, {"EXAM_LANG": lang, "EXAM_STYLE": style})
    print(f"\n已写入 {path}")
    print(f"  语言   = {lang}")
    print(f"  代码模式 = {style}")
    print("\n直接双击 start-exam.bat 开始笔试。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
