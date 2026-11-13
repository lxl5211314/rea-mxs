"""速答与完整回答并行时，完整回答的首字会不会被拖慢。

用法：python quick_bench.py [有/无速答]  默认对比两种
"""
from __future__ import annotations

import threading
import time

import mvp

Q = "请做一下自我介绍"


def run(with_quick: bool) -> tuple[float, float, float]:
    b = mvp.Brain("Java 后端工程师", "5 年 Java，主导订单中心重构")
    b.warm(True)
    first: list[float] = []
    t0 = time.time()
    q_t: list[float] = []
    if with_quick:
        def _q():
            bq = b.quick(Q)
            q_t.append(time.time() - t0)
            print(f"  速答 {q_t[-1]:.2f}s {bq}", flush=True)
        threading.Thread(target=_q, daemon=True).start()

    def on_first():
        first.append(time.time() - t0)

    text = b.answer(Q, lambda p: None, on_first=on_first)
    return (q_t[0] if q_t else -1), first[0], time.time() - t0, len(text)


if __name__ == "__main__":
    for flag in (False, True):
        q, f, total, n = run(flag)
        print(f"quick={'on' if flag else 'off'} 首字 {f:.2f}s 总 {total:.2f}s 速答 {q:.2f}s {n}字", flush=True)
