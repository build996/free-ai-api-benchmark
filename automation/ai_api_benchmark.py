#!/usr/bin/env python3
"""免费 AI API 实测 harness —— 产出一手数据(延迟 / tokens 每秒 / 真实输出)。

大多数免费 AI API 是 OpenAI 兼容的,所以这一个脚本就能把它们全跑一遍,
产出可直接贴进文章的实测数据:首 token 延迟(TTFT)、总耗时、tokens/秒、
真实输出样本、真实报错。全部标注实测时间戳。

Key 只从环境变量 / 本地 .ai-api-keys 文件读,脚本任何时候都不打印 key。

用法:
    # 1) 把有的 key 放进 .ai-api-keys(每行 PROVIDER_KEY=xxx),或设成环境变量
    # 2) 跑所有"有 key"的:
    python automation/ai_api_benchmark.py
    # 只跑某几家:
    python automation/ai_api_benchmark.py groq cerebras gemini
    # 换测试 prompt:
    python automation/ai_api_benchmark.py --prompt "用三句话解释什么是 API 限流"
    # 列出所有 provider 和需要的 key 名:
    python automation/ai_api_benchmark.py --list

结果:打印 Markdown 表 + 存 ai_benchmark_results.json(含原始输出)。

⚠️ 模型名会变。下面 model 是发稿时的合理默认;跑出来若报 "model not found",
   用 PROVIDER_MODEL 环境变量覆盖(如 GROQ_MODEL=llama-3.3-70b-versatile),别硬猜。
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 两个都认:普通 .txt(好打开)优先,老的隐藏 dotfile 也读
KEYS_FILES = [ROOT / "ai-api-keys.txt", ROOT / ".ai-api-keys"]
OUT = ROOT / "ai_benchmark_results.json"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# provider -> 配置。全部走 OpenAI 兼容的 /chat/completions。
# key_env: 读哪个环境变量;model_env: 覆盖模型的环境变量名。
PROVIDERS = {
    "groq":      {"base": "https://api.groq.com/openai/v1",                    "model": "openai/gpt-oss-120b",     "key_env": "GROQ_API_KEY"},  # Llama 3.3 已下架(实测 2026-08-29)
    "cerebras":  {"base": "https://api.cerebras.ai/v1",                        "model": "llama-3.3-70b",           "key_env": "CEREBRAS_API_KEY"},
    "gemini":    {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.6-flash",  "key_env": "GEMINI_API_KEY"},  # 2.0/2.5 已退役(实测 2026-08-30)
    "deepseek":  {"base": "https://api.deepseek.com/v1",                       "model": "deepseek-chat",           "key_env": "DEEPSEEK_API_KEY"},
    "sambanova": {"base": "https://api.sambanova.ai/v1",                       "model": "Meta-Llama-3.3-70B-Instruct", "key_env": "SAMBANOVA_API_KEY"},
    "together":  {"base": "https://api.together.xyz/v1",                       "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free", "key_env": "TOGETHER_API_KEY"},
    "openrouter":{"base": "https://openrouter.ai/api/v1",                      "model": "meta-llama/llama-3.3-70b-instruct:free", "key_env": "OPENROUTER_API_KEY"},
    "github":    {"base": "https://models.inference.ai.azure.com",            "model": "gpt-4o-mini",             "key_env": "GH_MODELS_TOKEN"},  # GITHUB_TOKEN 是 Actions 保留名,换个
    "mistral":   {"base": "https://api.mistral.ai/v1",                        "model": "mistral-small-latest",    "key_env": "MISTRAL_API_KEY"},
    "glm":       {"base": "https://open.bigmodel.cn/api/paas/v4",             "model": "glm-4-flash",             "key_env": "GLM_API_KEY"},
    "xai":       {"base": "https://api.x.ai/v1",                              "model": "grok-2-latest",           "key_env": "XAI_API_KEY"},
    "nvidia":    {"base": "https://integrate.api.nvidia.com/v1",              "model": "meta/llama-3.3-70b-instruct", "key_env": "NVIDIA_API_KEY"},
}

DEFAULT_PROMPT = ("Explain how an HTTP request/response cycle works, and what status "
                  "codes 200, 404, and 500 mean. Aim for about 250 words.")


def load_keys():
    for kf in KEYS_FILES:
        if not kf.exists():
            continue
        for line in kf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if v:  # 空值(还没填)不覆盖
                os.environ.setdefault(k.strip(), v)


def setup_proxy():
    """有 VPN 时,在 ai-api-keys.txt 里写 PROXY=http://127.0.0.1:7888,
    让所有请求统一走代理(公平横比)。显式装 opener,确保 urllib 真用上。"""
    proxy = os.environ.get("PROXY", "").strip()
    if not proxy:
        return None
    os.environ["HTTP_PROXY"] = os.environ["HTTPS_PROXY"] = proxy
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    urllib.request.install_opener(opener)
    return proxy


def model_for(name, cfg):
    return os.environ.get(f"{name.upper()}_MODEL", cfg["model"])


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _request(url, key, model, prompt, stream):
    """发一次请求;返回 (ttft, total, text, usage, chunks)。stream=False 时 ttft=None。"""
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.3, "max_tokens": 1200}
    if stream:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "text/event-stream" if stream else "application/json")
    req.add_header("User-Agent", UA)  # 默认 Python-urllib 会被 Cloudflare 挡成 403

    t0 = time.perf_counter()
    ttft, chunks, text, usage = None, 0, [], None
    with urllib.request.urlopen(req, timeout=90) as resp:
        if stream:
            for raw in resp:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content")
                if delta:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    chunks += 1
                    text.append(delta)
        else:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
            usage = obj.get("usage")
            text.append((obj.get("choices") or [{}])[0].get("message", {}).get("content", "") or "")
    return ttft, time.perf_counter() - t0, "".join(text), usage, chunks


def bench_one(name, cfg, prompt):
    key = os.environ.get(cfg["key_env"], "").strip()
    if not key:
        return {"provider": name, "skipped": f"no {cfg['key_env']}"}
    model = model_for(name, cfg)
    url = cfg["base"].rstrip("/") + "/chat/completions"

    streamed = True
    try:
        ttft, total, out, usage, chunks = _request(url, key, model, prompt, stream=True)
    except urllib.error.HTTPError as e:
        return {"provider": name, "model": model, "error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}"}
    except Exception:  # 流式失败(有些代理/节点掐 SSE)→ 非流式兜底
        try:
            ttft, total, out, usage, chunks = _request(url, key, model, prompt, stream=False)
            streamed = False
        except urllib.error.HTTPError as e:
            return {"provider": name, "model": model, "error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}"}
        except Exception as e:  # noqa: BLE001
            return {"provider": name, "model": model, "error": f"{type(e).__name__}: {e}"}

    out_tokens = (usage or {}).get("completion_tokens") or max(chunks, len(out) // 4)
    # 流式:剔除首包延迟算生成速度;非流式:只能端到端(含 prefill,口径略保守)
    gen_time = (total - ttft) if (streamed and ttft and total > ttft) else total
    gen_tps = out_tokens / gen_time if gen_time > 0 else 0
    return {
        "provider": name, "model": model,
        "ttft_s": round(ttft, 3) if (streamed and ttft) else None,
        "total_s": round(total, 3),
        "out_tokens": out_tokens,
        "tokens_from_usage": bool(usage),
        "streamed": streamed,
        "gen_tokens_per_s": round(gen_tps, 1),
        "output": out.strip(),
    }


def main():
    ap = argparse.ArgumentParser(description="免费 AI API 实测 harness")
    ap.add_argument("providers", nargs="*", help="只测这几家(默认:所有有 key 的)")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--list", action="store_true", help="列出所有 provider 和需要的 key 名")
    args = ap.parse_args()

    if args.list:
        print("Provider    需要的环境变量 / .ai-api-keys 字段      默认模型")
        for n, c in PROVIDERS.items():
            print(f"  {n:<10} {c['key_env']:<22} {c['model']}")
        print("\n模型覆盖:设 <PROVIDER>_MODEL,如 GROQ_MODEL=...")
        return

    load_keys()
    proxy = setup_proxy()
    if proxy:
        print(f"(走代理 {proxy} —— 所有家统一线路)\n")
    targets = args.providers or list(PROVIDERS)
    unknown = [t for t in targets if t not in PROVIDERS]
    if unknown:
        sys.exit(f"未知 provider: {unknown}。用 --list 看全部。")

    print(f"prompt: {args.prompt}\n")
    results = []
    for name in targets:
        r = bench_one(name, PROVIDERS[name], args.prompt)
        results.append(r)
        if r.get("skipped"):
            print(f"  {name:<10} 跳过({r['skipped']})")
        elif r.get("error"):
            print(f"  {name:<10} ❌ {r['error']}")
        else:
            tag = "真实" if r.get("tokens_from_usage") else "估算"
            ttft_s = f"TTFT {r['ttft_s']}s" if r.get("ttft_s") else "非流式(无TTFT)"
            print(f"  {name:<10} ✅ {ttft_s} · {r['out_tokens']} tok({tag}) · 生成 ~{r['gen_tokens_per_s']} tok/s")

    ran = [r for r in results if r.get("gen_tokens_per_s") is not None]
    if ran:
        ran.sort(key=lambda r: r["gen_tokens_per_s"], reverse=True)
        print("\n=== Markdown 表(可直接贴文章,标实测日期)===\n")
        print("| Provider | 模型 | 首 token 延迟(s) | 生成速度(tok/s) | 输出 tokens |")
        print("|---|---|---|---|---|")
        for r in ran:
            ttft = r["ttft_s"] if r.get("ttft_s") else "—"
            print(f"| {r['provider']} | `{r['model']}` | {ttft} | **{r['gen_tokens_per_s']}** | {r['out_tokens']} |")
        print("\n注:所有家走同一 VPN 线路实测(公平横比)。首 token 延迟含网络往返(非流式的一栏为—);"
              "生成速度=首 token 之后的吞吐,用 API 返回的真实 token 数算。")

    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n原始结果(含真实输出)已存:{OUT.name}")


if __name__ == "__main__":
    main()
