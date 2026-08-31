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
    "gemini":    {"base": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-3.6-flash",  "key_env": "GEMINI_API_KEY"},  # 2.0/2.5 已退役(实测 2026-08-30)
    "deepseek":  {"base": "https://api.deepseek.com/v1",                       "model": "deepseek-chat",           "key_env": "DEEPSEEK_API_KEY"},
    "openrouter":{"base": "https://openrouter.ai/api/v1",                      "model": "nvidia/nemotron-3-super-120b-a12b:free", "key_env": "OPENROUTER_API_KEY"},  # gemma:free 常 429,换 nemotron(实测 2026-08-31)
    "github":    {"base": "https://models.github.ai/inference",              "model": "openai/gpt-4o-mini",      "key_env": "GH_MODELS_TOKEN"},  # 旧 azure endpoint 已失效,换 models.github.ai(2026-08-31)
    "mistral":   {"base": "https://api.mistral.ai/v1",                        "model": "mistral-small-latest",    "key_env": "MISTRAL_API_KEY"},
    "glm":       {"base": "https://open.bigmodel.cn/api/paas/v4",             "model": "glm-4-flash",             "key_env": "GLM_API_KEY"},
    "nvidia":    {"base": "https://integrate.api.nvidia.com/v1",              "model": "nvidia/nemotron-3-super-120b-a12b", "key_env": "NVIDIA_API_KEY"},  # nemotron-70b 账号无权限;super-120b 实测可用(2026-08-31)
}

# 同模型跨平台"对决":一个开源模型 → 各平台上它的 model id(命名各不同)。
# 只测有 key 的平台。id 需逐平台核实(有的可能已更名/下架,跑出来会报错就换)。
SHOOTOUTS = {
    # nemotron-3-super-120b —— NVIDIA 直连 vs OpenRouter,同一个模型(免费层塌到现在少数还能同款横比的)
    "nemotron-super-120b": {
        "nvidia":     "nvidia/nemotron-3-super-120b-a12b",       # 已核实可用
        "openrouter": "nvidia/nemotron-3-super-120b-a12b:free",  # 已核实在 OpenRouter 免费
    },
}

DEFAULT_PROMPT = ("Explain how an HTTP request/response cycle works, and what status "
                  "codes 200, 404, and 500 mean. Aim for about 250 words.")

# 一个平台上值得逐个测的模型(--models <provider>)。只列免费档能调的。
PROVIDER_MODELS = {
    "groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b",
             "qwen/qwen3.6-27b", "groq/compound-mini"],
    # NVIDIA 托管 83 个模型,横跨各家厂商。挑代表性的:自家 nemotron 三档 + 各厂旗舰 + 小模型
    "nvidia": [
        "nvidia/nemotron-3-super-120b-a12b",      # 自家大模型
        "nvidia/nemotron-3-nano-30b-a3b",          # 自家小模型
        "nvidia/nemotron-3.5-lightning-30b-a3b",   # 自家主打速度
        "deepseek-ai/deepseek-v4-flash-0731",      # DeepSeek 最新(直连已收费,这里还能白嫖)
        "moonshotai/kimi-k3",                      # Kimi 最新
        "minimaxai/minimax-m3",                    # MiniMax
        "google/gemma-4-31b-it",                   # Google 开源
        "mistralai/mistral-nemotron",              # Mistral×NVIDIA
        "meta/llama-3.1-nemotron-70b-instruct",    # Meta 系(经 NVIDIA 调优)
        "microsoft/phi-3.5-moe-instruct",          # 微软小模型
    ],
    "openrouter": ["nvidia/nemotron-3-super-120b-a12b:free", "google/gemma-4-31b-it:free",
                   "minimax/minimax-m3:free", "z-ai/glm-5.2:free"],
}

# 能力测试:每题给可判定的通过条件,报"通过/失败"而不是主观打分。
CAPABILITY_TASKS = [
    {
        "id": "json",
        "prompt": ('Return ONLY valid JSON, no markdown fence, no prose: '
                   '{"language":"Python","year":1991,"typed":false}. '
                   'Reply with exactly that object.'),
        "check": lambda t: _json_ok(t),
        "why": "指令遵循 / 结构化输出(能不能塞进代码管道)",
    },
    {
        "id": "code",
        "prompt": ("Write a Python function `is_palindrome(s)` that ignores case, spaces and "
                   "punctuation. Output ONLY the code, no explanation."),
        "check": lambda t: ("def is_palindrome" in t and "return" in t),
        "why": "写代码(能不能直接用)",
    },
    {
        "id": "chinese",
        "prompt": "用一句话解释什么是 API 限流,只用中文回答,不要英文。",
        "check": lambda t: (sum('一' <= c <= '鿿' for c in t) > 8),
        "why": "中文能力(中文项目能不能用)",
    },
    {
        "id": "needle",
        "prompt": ("Here is a config dump:\n" + ("noise_line=0\n" * 60) +
                   "SECRET_PORT=8471\n" + ("noise_line=1\n" * 60) +
                   "\nWhat is the value of SECRET_PORT? Answer with the number only."),
        "check": lambda t: "8471" in t,
        "why": "长上下文找信息(RAG 场景)",
    },
]


def _json_ok(text):
    t = text.strip().strip("`")
    if t.lower().startswith("json"):
        t = t[4:].strip()
    try:
        d = json.loads(t)
        return d.get("language") == "Python" and d.get("year") == 1991
    except Exception:
        return False


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


def bench_one(name, cfg, prompt, model=None):
    key = os.environ.get(cfg["key_env"], "").strip()
    if not key:
        return {"provider": name, "skipped": f"no {cfg['key_env']}"}
    model = model or model_for(name, cfg)
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


def run_capability(spec):
    """能力测试:一个平台(或指定模型)跑 4 个可判定的任务,报通过/失败 + 真实输出。"""
    prov, _, model = spec.partition(":")
    if prov not in PROVIDERS:
        sys.exit(f"未知 provider: {prov}")
    models = [model] if model else PROVIDER_MODELS.get(prov, [PROVIDERS[prov]["model"]])
    print(f"=== {prov} 能力测试(4 项固定任务,通过/失败可复现)===\n")
    table = []
    for m in models:
        row = {"model": m}
        marks = []
        for task in CAPABILITY_TASKS:
            r = bench_one(prov, PROVIDERS[prov], task["prompt"], model=m)
            if r.get("error") or r.get("skipped"):
                ok, note = False, (r.get("error") or r.get("skipped"))[:60]
            else:
                try:
                    ok = bool(task["check"](r.get("output", "")))
                except Exception:
                    ok = False
                note = (r.get("output", "") or "").strip().replace("\n", " ")[:70]
            row[task["id"]] = ok
            row[task["id"] + "_out"] = note
            marks.append(f"{task['id']}:{'✅' if ok else '❌'}")
        passed = sum(1 for t in CAPABILITY_TASKS if row.get(t["id"]))
        row["passed"] = passed
        table.append(row)
        print(f"  {m[-34:]:<34} {' '.join(marks)}  ({passed}/{len(CAPABILITY_TASKS)})")

    print("\n=== Markdown 表(可直接贴文章)===\n")
    print("| 模型 | 结构化 JSON | 写代码 | 中文 | 长上下文 | 通过 |")
    print("|---|---|---|---|---|---|")
    for r in table:
        c = lambda k: "✅" if r.get(k) else "❌"  # noqa: E731
        print(f"| `{r['model']}` | {c('json')} | {c('code')} | {c('chinese')} | {c('needle')} | {r['passed']}/4 |")
    print("\n任务:①只输出合法 JSON(指令遵循)②写可用的 Python 函数 ③纯中文回答 ④从 120 行噪声里找出指定值。")
    OUT.with_name("ai_capability_results.json").write_text(
        json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"原始输出已存:ai_capability_results.json")


def main():
    ap = argparse.ArgumentParser(description="免费 AI API 实测 harness")
    ap.add_argument("providers", nargs="*", help="只测这几家(默认:所有有 key 的)")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--list", action="store_true", help="列出所有 provider 和需要的 key 名")
    ap.add_argument("--shootout", help="同模型跨平台对决,如 nemotron-super-120b")
    ap.add_argument("--models", help="测一个平台内的多个模型,如 groq / nvidia / openrouter")
    ap.add_argument("--capability", help="能力测试(JSON/代码/中文/长上下文),传 provider 或 provider:model")
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
    if args.capability:
        run_capability(args.capability)
        return

    if args.models:
        prov = args.models
        if prov not in PROVIDER_MODELS:
            sys.exit(f"没配置 {prov} 的模型列表。有:{list(PROVIDER_MODELS)}")
        pairs = [(prov, m) for m in PROVIDER_MODELS[prov]]
        print(f"=== {prov} 平台内多模型实测(每个模型跑同一 prompt)===")
    elif args.shootout:
        so = SHOOTOUTS.get(args.shootout)
        if not so:
            sys.exit(f"未知 shootout: {args.shootout}。有:{list(SHOOTOUTS)}")
        pairs = [(p, m) for p, m in so.items() if p in PROVIDERS]
        print(f"=== 对决:{args.shootout}(同模型跨平台,只测有 key 的)===")
    else:
        targets = args.providers or list(PROVIDERS)
        unknown = [t for t in targets if t not in PROVIDERS]
        if unknown:
            sys.exit(f"未知 provider: {unknown}。用 --list 看全部。")
        pairs = [(t, None) for t in targets]

    print(f"prompt: {args.prompt}\n")
    results = []
    for name, model in pairs:
        label = (model or name)[-34:] if args.models else name
        r = bench_one(name, PROVIDERS[name], args.prompt, model=model)
        results.append(r)
        if r.get("skipped"):
            print(f"  {label:<34} 跳过({r['skipped']})")
        elif r.get("error"):
            print(f"  {label:<34} ❌ {r['error'][:120]}")
        elif args.models:
            tag = "真实" if r.get("tokens_from_usage") else "估算"
            print(f"  {label:<34} ✅ {r['out_tokens']} tok({tag}) · ~{r['gen_tokens_per_s']} tok/s")
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
