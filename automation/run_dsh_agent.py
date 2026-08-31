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
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from deepseek_harness import DeepSeekHarness  # noqa: E402

WORKSPACE = os.environ.get("DSH_WORKSPACE", "/tmp/ws")
HOME = os.environ.get("DSH_HOME", "/tmp/dsh-home")


def write_custom_provider_settings():
    """按官方 providers.md 的格式,把任意 OpenAI 兼容端点注册成自定义 provider。

    dsh 不是靠 Config 里的 base_url 路由的,而是读 $DSH_HOME/settings.yaml。
    """
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "").strip()
    model = os.environ.get("DSH_MODEL", "").strip()
    if not base_url or not model:
        return None
    pid = "benchgw"
    home = Path(HOME)
    home.mkdir(parents=True, exist_ok=True)
    settings = f"""llm-pi-ai:
  providers:
    {pid}:
      apiKeyEnv: BENCH_API_KEY
      api: openai-completions
      baseURL: {base_url}
      models:
        - id: {model}
"""
    (home / "settings.yaml").write_text(settings, encoding="utf-8")
    # 供 apiKeyEnv 引用
    os.environ["BENCH_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
    print(f"registered custom provider '{pid}' -> {base_url} ({model})")
    print(settings)
    return pid


def main():
    if len(sys.argv) < 2:
        sys.exit("need a task prompt")
    prompt = sys.argv[1]
    custom_pid = write_custom_provider_settings()

    params = set(inspect.signature(DeepSeekHarness.__init__).parameters)
    print("DeepSeekHarness accepts:", sorted(p for p in params if p != "self"))

    wanted = {
        # 用上面注册的自定义 provider id;没注册成功才退回 deepseek-official
        "provider": custom_pid or os.environ.get("DSH_PROVIDER", "deepseek-official"),
        "model": os.environ.get("DSH_MODEL", "deepseek-v4-flash"),
        # 显式传 key/base_url —— 别指望它一定会读环境变量
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", ""),
        "cwd": WORKSPACE,
        "workspace": WORKSPACE,
        "session_root": HOME,
        "dsh_home": HOME,
        "home": HOME,
        "profile": "sdk-minimal",
    }

    if "config" in params:
        # 这个 SDK 版本只吃一个 config 对象
        import deepseek_harness as dh
        cfg_cls = None
        for attr in dir(dh):
            if "Config" in attr:
                cfg_cls = getattr(dh, attr)
                print("found config class:", attr)
                break
        if cfg_cls is None:
            sys.exit("SDK wants config= but exports no Config class")
        cfg_params = set(inspect.signature(cfg_cls.__init__).parameters)
        print("Config accepts:", sorted(p for p in cfg_params if p != "self"))
        cfg_kw = {k: v for k, v in wanted.items() if k in cfg_params}
        print("passing to Config:", sorted(cfg_kw))
        harness = DeepSeekHarness(config=cfg_cls(**cfg_kw))
    else:
        kw = {k: v for k, v in wanted.items() if k in params}
        print("passing:", sorted(kw))
        harness = DeepSeekHarness(**kw)

    with harness as h:
        result = h.run(prompt, session_id="bench-run")
    final = getattr(result, "final_response", result)
    print("FINAL RESPONSE:")
    print(final)
    if not str(final).strip():
        print("WARNING: empty final response — the agent likely never ran "
              "(check api_key/base_url/provider wiring, not model capability)")


if __name__ == "__main__":
    main()
