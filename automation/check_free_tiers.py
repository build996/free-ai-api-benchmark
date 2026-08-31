#!/usr/bin/env python3
"""Pull free-tier numbers straight from providers' own pricing pages.

Free tiers change quietly and articles keep quoting the old figure — we had
Turso's paid 9 GB tier written up as its free allowance in five places. This
fetches each pricing page, strips it to text, and prints the lines around the
free-tier limits so they can be compared against what an article claims.

    python automation/check_free_tiers.py              # every provider
    python automation/check_free_tiers.py turso neon   # a subset

It deliberately does NOT try to parse a single number out of the page — pricing
layouts differ too much and a wrong auto-extraction is worse than none. It gives
you the relevant text; you read it.
"""
import argparse
import html
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PAGES = {
    "turso":     ("https://turso.tech/pricing",     r"Databases Free"),
    "render":    ("https://render.com/pricing",     r"Free"),
    "railway":   ("https://railway.com/pricing",    r"Free|Trial|Hobby"),
    "supabase":  ("https://supabase.com/pricing",   r"Free"),
    "neon":      ("https://neon.com/pricing",       r"Free"),
    "upstash":   ("https://upstash.com/pricing",    r"Free"),
    "vercel":    ("https://vercel.com/pricing",     r"Hobby|Free"),
    "netlify":   ("https://www.netlify.com/pricing/", r"Free|Starter"),
    "modal":     ("https://modal.com/pricing",      r"Free|credit"),
    "qdrant":    ("https://qdrant.tech/pricing/",   r"Free"),
}

KEYWORDS = ("gb", "mb", "storage", "database", "million", "billion",
            "month", "hour", "credit", "limit", "request", "build", "bandwidth")


def fetch(url: str) -> str:
    req = urllib.request.Request(url)
    req.add_header("User-Agent",
                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    req.add_header("Accept-Language", "en-US,en;q=0.9")
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def to_text(raw: str) -> str:
    raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
    raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S | re.I)
    txt = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", txt)


def setup_proxy():
    proxy = os.environ.get("PROXY", "").strip()
    if not proxy:
        kf = ROOT / "ai-api-keys.txt"
        if kf.exists():
            m = re.search(r"^\s*PROXY=(.+)$", kf.read_text(encoding="utf-8"), re.M)
            if m:
                proxy = m.group(1).strip()
    if proxy:
        urllib.request.install_opener(urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})))
    return proxy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("providers", nargs="*")
    ap.add_argument("--chars", type=int, default=600, help="context to print")
    args = ap.parse_args()

    proxy = setup_proxy()
    if proxy:
        print(f"(via proxy {proxy})\n")

    targets = args.providers or list(PAGES)
    for name in targets:
        if name not in PAGES:
            print(f"unknown: {name}"); continue
        url, anchor = PAGES[name]
        print(f"===== {name} — {url} =====")
        try:
            txt = to_text(fetch(url))
        except Exception as e:  # noqa: BLE001
            print(f"  fetch failed: {type(e).__name__}: {e}\n")
            continue

        m = re.search(anchor, txt, re.I)
        if m:
            print(" ", txt[m.start():m.start() + args.chars].strip(), "\n")
        else:
            # no anchor — show sentences that look like limits
            hits = [seg.strip() for seg in re.split(r"(?<=[.!?]) ", txt)
                    if "free" in seg.lower() and any(k in seg.lower() for k in KEYWORDS)]
            if hits:
                for h in hits[:5]:
                    print("  -", h[:180])
                print()
            else:
                print("  (nothing matched — the page is probably JS-rendered; check by hand)\n")


if __name__ == "__main__":
    raise SystemExit(main())
