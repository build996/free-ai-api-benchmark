#!/usr/bin/env python3
"""用 DeepSeek Harness 跑一个 agent 任务,后端可换成任意 OpenAI 兼容的免费 API。

dsh 还是 developer preview,已发布的 pip SDK 和仓库示例可能对不上,
所以这里先用 inspect 探明真实签名,只传它认识的参数。

环境变量:
  DEEPSEEK_API_KEY   后端 key
  DEEPSEEK_BASE_URL  OpenAI 兼容端点
  DSH_MODEL          模型 id
用法: python run_dsh_agent.py "任务描述"
"""
import inspect
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from deepseek_harness import DeepSeekHarness  # noqa: E402

WORKSPACE = os.environ.get("DSH_WORKSPACE", "/tmp/ws")
HOME = os.environ.get("DSH_HOME", "/tmp/dsh-home")


def main():
    if len(sys.argv) < 2:
        sys.exit("need a task prompt")
    prompt = sys.argv[1]

    params = set(inspect.signature(DeepSeekHarness.__init__).parameters)
    print("SDK accepts:", sorted(p for p in params if p != "self"))

    candidates = [
        ("provider", os.environ.get("DSH_PROVIDER", "deepseek-official")),
        ("model", os.environ.get("DSH_MODEL", "deepseek-v4-flash")),
        ("cwd", WORKSPACE),
        ("workspace", WORKSPACE),
        ("dsh_home", HOME),
        ("home", HOME),
        ("profile", "sdk-minimal"),
    ]
    kw = {k: v for k, v in candidates if k in params}
    print("passing:", sorted(kw))

    with DeepSeekHarness(**kw) as h:
        result = h.run(prompt, session_id="bench-run")
    print("FINAL RESPONSE:")
    print(getattr(result, "final_response", result))


if __name__ == "__main__":
    main()
