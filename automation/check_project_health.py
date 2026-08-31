#!/usr/bin/env python3
"""Flag open-source projects we recommend that have gone quiet.

A tool review ages badly in a specific way: the tool stops being maintained and
the article keeps recommending it. This checks the GitHub signals that actually
matter — last commit, last release, archived flag — and prints anything stale.

    python automation/check_project_health.py            # all tracked projects
    python automation/check_project_health.py --days 120 # stricter threshold

Needs GH_TOKEN (or a token in .gh-credentials) for a sane rate limit.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# repo -> the main-site article it appears in (so a stale result is actionable)
TRACKED = {
    "ollama/ollama":            "ollama-run-ai-models-locally",
    "langgenius/dify":          "dify-free-ai-app-builder",
    "n8n-io/n8n":               "n8n-workflow-automation",
    "open-webui/open-webui":    "open-webui-self-hosted-ai",
    "crewAIInc/crewAI":         "crewai-multi-agent-framework",
    "Aider-AI/aider":           "aider-free-ai-coding-cli",
    "cline/cline":              "cline-free-ai-coding-agent",
    "browser-use/browser-use":  "browser-use-ai-agent",
    "unclecode/crawl4ai":       "crawl4ai-web-crawler",
    "firecrawl/firecrawl":      "firecrawl-free-scraping-api",
    "coollabsio/coolify":       "coolify-self-hosted-paas",
    "langfuse/langfuse":        "langfuse-llm-observability",
    "pocketbase/pocketbase":    "pocketbase-free-backend",
    "appwrite/appwrite":        "appwrite-firebase-alternative",
    "BerriAI/litellm":          "litellm-free-llm-gateway",
    "deepseek-ai/deepseek-harness": "deepseek-harness-review",
}


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t.strip()
    cred = ROOT / ".gh-credentials"
    if cred.exists():
        m = re.search(r"^(?:GH_TOKEN|GITHUB_TOKEN|TOKEN)=(.+)$",
                      cred.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def api(path, tok):
    req = urllib.request.Request(f"https://api.github.com/{path}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "toolfreebie-health/1.0")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def days_since(iso):
    if not iso:
        return None
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - d).days


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90,
                    help="flag projects with no commit in this many days (default 90)")
    args = ap.parse_args()

    tok = token()
    if not tok:
        print("(no token — running unauthenticated, may hit rate limits)\n")

    rows, stale = [], []
    for repo, slug in TRACKED.items():
        d = api(f"repos/{repo}", tok)
        if not d:
            print(f"  ? {repo}: could not fetch")
            continue
        commit_age = days_since(d.get("pushed_at"))
        rel = api(f"repos/{repo}/releases/latest", tok)
        rel_age = days_since((rel or {}).get("published_at"))
        row = {
            "repo": repo, "slug": slug,
            "stars": d.get("stargazers_count"),
            "commit_days": commit_age,
            "release_days": rel_age,
            "release_tag": (rel or {}).get("tag_name"),
            "open_issues": d.get("open_issues_count"),
            "archived": d.get("archived"),
        }
        rows.append(row)
        if row["archived"] or (commit_age or 0) > args.days or (rel_age or 0) > 365:
            stale.append(row)

    rows.sort(key=lambda r: r["commit_days"] or 0, reverse=True)
    print(f"{'repo':<32}{'stars':>8}{'last commit':>14}{'last release':>16}")
    for r in rows:
        rel = f"{r['release_days']}d ({r['release_tag']})" if r["release_days"] is not None else "none"
        mark = " ⚠️" if r in stale else ""
        print(f"{r['repo']:<32}{r['stars']:>8}{str(r['commit_days'])+'d':>14}{rel:>16}{mark}")

    if stale:
        print(f"\n⚠️  {len(stale)} project(s) need an article update:\n")
        for r in stale:
            why = []
            if r["archived"]:
                why.append("ARCHIVED")
            if (r["commit_days"] or 0) > args.days:
                why.append(f"no commit in {r['commit_days']} days")
            if (r["release_days"] or 0) > 365:
                why.append(f"no release in {r['release_days']} days")
            print(f"  {r['repo']} — {', '.join(why)}")
            print(f"      → https://toolfreebie.com/{r['slug']}/  ({r['open_issues']} open issues)")
    else:
        print("\n✅ every tracked project is active")

    out = ROOT / "project_health.json"
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"\nraw -> {out.name}")


if __name__ == "__main__":
    raise SystemExit(main())
