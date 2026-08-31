#!/usr/bin/env python3
"""Archive one benchmark run into results/ and refresh the README table.

Run right after ai_api_benchmark.py inside CI. It:
  1. copies ai_benchmark_results.json to results/YYYY-MM-DD.json (dated history)
  2. rewrites the table between the README markers with the newest numbers

The point is a public, dated record: anyone can see when a figure was measured
and how it moved, instead of trusting an undated blog claim.
"""
import io
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LATEST = ROOT / "ai_benchmark_results.json"
RESULTS = ROOT / "results"
README = ROOT / "README.md"

START = "<!-- BENCHMARK_TABLE_START -->"
END = "<!-- BENCHMARK_TABLE_END -->"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not LATEST.exists():
        print("no ai_benchmark_results.json — nothing to record")
        return 0

    data = json.loads(LATEST.read_text(encoding="utf-8"))
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    RESULTS.mkdir(exist_ok=True)
    dated = RESULTS / f"{day}.json"
    shutil.copy(LATEST, dated)
    print(f"archived -> results/{dated.name}")

    # 超过这个值几乎必是"整段缓冲后一次性吐出"造成的假高值
    # (gen_time 趋近 0)。宁可漏报也不发布不可信的数字。
    SANITY_CAP = 1500.0

    ok, suspect = [], []
    for r in data:
        tps = r.get("gen_tokens_per_s")
        if not tps:
            continue
        (suspect if tps > SANITY_CAP else ok).append(r)
    errs = [r for r in data if r.get("error")]
    for r in suspect:
        print(f"  ! dropped {r['provider']}/{r['model']}: {r['gen_tokens_per_s']} tok/s "
              f"exceeds sanity cap — likely a buffered response")
    if not ok and not errs:
        print("no usable rows; README left alone")
        return 0

    ok.sort(key=lambda r: r["gen_tokens_per_s"], reverse=True)

    lines = [
        f"*Last run: {day} (UTC), from a US GitHub Actions runner.*",
        "",
        "| Provider | Model | tokens/s |",
        "|---|---|---|",
    ]
    for r in ok:
        lines.append(f"| {r['provider']} | `{r['model']}` | **{r['gen_tokens_per_s']}** |")

    if suspect:
        lines += ["", "Excluded as implausible (buffered responses inflate throughput):", ""]
        for r in suspect:
            lines.append(f"- {r['provider']} / `{r['model']}` — measured {r['gen_tokens_per_s']} tok/s")

    if errs:
        lines += ["", "Providers that failed this run:", ""]
        for r in errs:
            msg = str(r["error"])
            # keep it short and never leak a key
            msg = msg.split("\n")[0][:110]
            lines.append(f"- **{r['provider']}** — {msg}")

    table = "\n".join(lines)

    if not README.exists():
        print("no README; skipping refresh")
        return 0

    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        print("README markers missing; archived only")
        return 0

    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    README.write_text(f"{head}{START}\n{table}\n{END}{tail}", encoding="utf-8")
    print(f"README table refreshed: {len(ok)} ok, {len(errs)} failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
