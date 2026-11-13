"""对比智能交付 relay 上各模型/思考档位的首字延迟（真实 system prompt + 真实问题）。

用法: python bench_llm2.py
结果写 bench_llm2.log（utf-8，避免 PowerShell GBK 乱码）。
"""
import os
import sys
import time

import mvp

Q = "你在上一家公司遇到过的最大技术挑战是什么？怎么解决的？"

CONFIGS = [
    ("deepseek-v4.1-flash", "minimal", ""),
    ("deepseek-v4.1-flash", "high", ""),
    ("deepseek-v4.1-flash", "", '{"thinking":{"type":"disabled"}}'),
    ("GLM-5.3", "", ""),
    ("GLM-5.3", "minimal", ""),
    ("deepseek-v4.1-p", "minimal", ""),
    ("DeepSeek-V4-Pro", "minimal", ""),
]

lines: list[str] = []


def log(s: str = "") -> None:
    print(s, flush=True)
    lines.append(s)


def run(model: str, effort: str, extra: str, round_no: int) -> None:
    mvp.LLM_MODEL = model
    mvp.LLM_REASONING_EFFORT = effort
    mvp.LLM_EXTRA_JSON = extra
    b = mvp.Brain(role=os.getenv("ROLE", "后端工程师"), resume=os.getenv("RESUME", ""))
    t0 = time.time()
    st = {"r": 0.0, "c": 0.0, "n": 0, "rn": 0}

    def on_reason(piece: str) -> None:
        st["rn"] += 1
        if not st["r"]:
            st["r"] = time.time() - t0

    def on_first() -> None:
        st["c"] = time.time() - t0

    def on_delta(piece: str) -> None:
        st["n"] += 1

    try:
        text = b.answer(Q, on_delta, on_reason, on_first)
        total = time.time() - t0
        log(f"[{round_no}] {model} effort={effort or '-'} extra={extra or '-'} "
            f"rTTFT={st['r']:.2f}s cTTFT={st['c']:.2f}s total={total:.2f}s "
            f"chars={len(text)} rchunks={st['rn']} | {text[:40]}")
    except Exception as e:
        log(f"[{round_no}] {model} effort={effort or '-'} extra={extra or '-'} FAIL {type(e).__name__}: {e}")


def main() -> int:
    log(f"# base={mvp.OPENAI_BASE_URL} q={Q}")
    for i, (m, e, x) in enumerate(CONFIGS, 1):
        run(m, e, x, i)
    log("# --- 第二轮（同提问，看缓存是否生效） ---")
    for i, (m, e, x) in enumerate(CONFIGS[:4], 11):
        run(m, e, x, i)
    with open("bench_llm2.log", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
