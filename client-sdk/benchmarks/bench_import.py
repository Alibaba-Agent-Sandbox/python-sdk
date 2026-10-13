"""模块导入时间基准测试。"""

import time


def bench_import():
    modules = [
        "agent_sandbox",
        "agent_sandbox.models",
        "agent_sandbox.transport",
        "agent_sandbox.protocol",
        "agent_sandbox.api",
        "agent_sandbox.agent",
        "agent_sandbox.declarative",
        "agent_sandbox.session",
    ]
    for mod in modules:
        start = time.perf_counter()
        __import__(mod)
        elapsed = time.perf_counter() - start
        print(f"  import {mod}: {elapsed:.3f}s")


if __name__ == "__main__":
    print("=== Import Benchmark ===")
    bench_import()
