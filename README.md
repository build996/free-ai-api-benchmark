# Free AI API Benchmark

Reproducible latency + throughput benchmark for the **free tiers** of popular AI APIs
(Groq, Google Gemini, SambaNova, NVIDIA NIM, OpenRouter, Mistral, and more), run from a
neutral **US GitHub Actions runner** so every provider is measured over the same route — a fair comparison.

Pairs with the hands-on reviews at **[toolfreebie.com](https://toolfreebie.com)**.

## What it measures
- **TTFT** (time to first token) and **generation throughput** (tokens/sec), computed from the API's own `usage` token counts.
- Auto-falls back to non-streaming for providers whose SSE stream is blocked.

## Run it
1. Add each provider's key as an **Actions secret** (`GROQ_API_KEY`, `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `SAMBANOVA_API_KEY`, `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `TOGETHER_API_KEY`, `GLM_API_KEY`, `GH_MODELS_TOKEN`).
2. Run the **AI API Benchmark** workflow (Actions tab → Run workflow). Results appear in the job summary + as an artifact.

MIT.
