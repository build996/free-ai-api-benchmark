# Free AI API Benchmark

Reproducible benchmarks for the **free tiers** of the major AI APIs — measured from a neutral US GitHub Actions runner so every provider is tested over the same route.

Unlike vendor marketing pages, everything here is measured. Unlike most benchmark repos, it also tests whether models can **actually complete tasks**, not just how fast they emit tokens.

Pairs with the hands-on reviews at **[toolfreebie.com](https://toolfreebie.com)**.

---

## Latest results (2026-08-31)

### Generation throughput

<!-- BENCHMARK_TABLE_START -->
*Last run: 2026-08-31 (UTC), from a US GitHub Actions runner.*

| Provider | Model | tokens/s |
|---|---|---|
| groq | `openai/gpt-oss-120b` | **526.7** |
| mistral | `mistral-small-latest` | **166.6** |
| gemini | `gemini-3.6-flash` | **141.0** |
| openrouter | `nvidia/nemotron-3-super-120b-a12b:free` | **38.1** |
| nvidia | `nvidia/nemotron-3-super-120b-a12b` | **33.3** |
| glm | `glm-4-flash` | **20.2** |

Providers that failed this run:

- **github** — HTTP 410: {"error":{"code":"github_models_retirement_brownout","message":"GitHub Models is temporarily unavail
<!-- BENCHMARK_TABLE_END -->

This table is regenerated automatically by the weekly run — see [`results/`](results/) for every dated snapshot. Throughput is generation-only (excludes time to first token) and uses each API's own `usage` token counts. Free-tier capacity is shared, so expect ±30% between runs; the ranking is stable, the absolute numbers are a band.

### Which free tiers still exist

| Provider | Status (Aug 2026) |
|---|---|
| Groq | ✅ Free, no card |
| NVIDIA NIM | ✅ Free, no card, 83 models |
| OpenRouter | ✅ Free tier, no card |
| Google Gemini | ✅ Free, now defaults to reasoning models |
| Mistral | ✅ Free tier |
| **SambaNova** | ❌ `PAYMENT_METHOD_REQUIRED` — card now required |
| **Together** | ❌ Read-only until you deposit |
| **Cerebras** | ❌ Card required |

### Speech-to-text

Transcription speed is best read as a **realtime factor** — seconds of audio handled per second of wall clock.

| Model (Groq free tier) | 4 min of audio | Realtime | Transcript |
|---|---|---|---|
| `whisper-large-v3-turbo` | **1.53 s** | **160×** | 2,081 chars |
| `whisper-large-v3` | 1.85 s | 132× | 2,082 chars |

Turbo was 21% faster and produced a transcript one character different — no quality trade-off on this sample.

**Clip length changes the answer completely.** The same API and model measured **7.3×** on an 11-second clip and **160×** on a 4-minute one, because per-request overhead (handshake, upload, queueing) doesn't shrink with the audio. A realtime factor quoted without the clip length is meaningless — ours is measured on 4 minutes.

### Can these models actually run an agent?

Same models, driven through [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), given real jobs (fix a broken script, tidy a folder, summarise CSVs) and graded by **inspecting the filesystem afterwards** — not by reading the model's own claim of success.

| Model | Fix a two-bug script | Notes |
|---|---|---|
| Nemotron Super 120B | ✅ **43 s** | On a file task: reported success in 20 s having **moved zero files** |
| Kimi K3 | ✅ 56 s | Most reliable overall; also summarised 3 CSVs correctly |
| DeepSeek V4 Flash | ✅ 251 s | Slowest of the passes, despite "Flash" |
| Gemma 4 31B | ❌ | Hung until the 900 s timeout |

**Throughput does not predict agent performance.** Gemma 4 was second-fastest by tokens/s and never completed a task. Nemotron returned empty responses in the streaming benchmark and was the fastest agent. The two measure different things: typing speed vs decision quality.

---

## Gotchas worth knowing

- **`meta/llama-3.3-70b-instruct` is gone from NVIDIA NIM.** Nearly every NIM tutorial online still opens with it. It now hard-fails.
- **DeepSeek Harness + Groq fails silently** — empty response after ~1 s, no error, no log. NVIDIA's endpoint works. "OpenAI-compatible" describes request shape, not harness compatibility.
- **dsh has no documented headless CLI.** Use the Node API; the model belongs in the *plugin config*, not in `run()` (where it is silently ignored).
- **Some endpoints buffer the whole response** then flush it, which drives `total − ttft` toward zero and yields absurd throughput figures. The harness detects this and falls back to end-to-end timing.

## What it measures

- **TTFT** (time to first token) and **generation throughput**, from each API's own `usage` counts.
- **Shootout mode**: the same open-weight model across every platform that hosts it — the only fair cross-platform comparison, since platforms host different model mixes.
- **Capability tasks**: code, JSON, long-context, Chinese.
- **Speech-to-text**: realtime factor on a fixed public-domain recording (`automation/bench_transcribe.py`).
- **Agent tasks** via DeepSeek Harness, graded on filesystem state.

## Run it yourself

1. Add each provider's key as an **Actions secret** (`GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `GLM_API_KEY`, `GH_MODELS_TOKEN`, …).
2. Run the **AI API Benchmark** workflow (Actions → Run workflow). Results land in the job summary and as an artifact.
3. For agent tests, run the **DSH Agent Test** workflow.

Locally:

```bash
python automation/ai_api_benchmark.py                            # every provider with a key
python automation/ai_api_benchmark.py groq nvidia                # specific ones
python automation/ai_api_benchmark.py --shootout gpt-oss-120b    # same model, many platforms
python automation/ai_api_benchmark.py --list                     # what's configured
```

Keys come from environment variables or a local `ai-api-keys.txt` (gitignored). Set `PROXY=http://127.0.0.1:7890` if you need one.

> Agent tests execute shell commands generated by a model. They belong in a disposable container — which is why the workflow runs them in Actions, not on your laptop. See DeepSeek Harness's [SAFETY.md](https://github.com/deepseek-ai/deepseek-harness/blob/main/SAFETY.md).

## Related reading

- [Free AI APIs tested: which are still free (and fastest)](https://toolfreebie.com/free-ai-api-speed-test/)
- [We gave free AI models real agent jobs](https://toolfreebie.com/free-ai-models-agent-test/)
- [NVIDIA NIM free API: 83 models tested](https://toolfreebie.com/nvidia-nim-free-api/)
- [DeepSeek Harness review](https://toolfreebie.com/deepseek-harness-review/)
- [Groq free API tested](https://toolfreebie.com/groq-fastest-free-ai-api/)

MIT.
