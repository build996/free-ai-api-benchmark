#!/usr/bin/env python3
"""Benchmark free speech-to-text APIs on the same audio file.

Speed for transcription is best expressed as a **realtime factor**: how many
seconds of audio you process per second of wall clock. 60x means a one-minute
recording is done in one second. That number is comparable across providers in
a way "tokens/sec" is not.

Generates its own test audio (a spoken-word public-domain clip via TTS is not
available offline, so we synthesise a tone-free WAV of known length only when
no sample is supplied). Prefer passing a real speech file:

    python automation/bench_transcribe.py path/to/speech.wav

Providers are OpenAI-compatible /audio/transcriptions endpoints.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS_FILES = [ROOT / "ai-api-keys.txt", ROOT / ".ai-api-keys"]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/audio/transcriptions",
        "key_env": "GROQ_API_KEY",
        "model": "whisper-large-v3-turbo",
    },
    "groq-large": {
        "url": "https://api.groq.com/openai/v1/audio/transcriptions",
        "key_env": "GROQ_API_KEY",
        "model": "whisper-large-v3",
    },
}


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
            if v:
                os.environ.setdefault(k.strip(), v)


def setup_proxy():
    proxy = os.environ.get("PROXY", "").strip()
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        urllib.request.install_opener(opener)
    return proxy


def audio_duration(path: Path) -> float:
    """Duration in seconds. Tries ffprobe, then the WAV header."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=20)
        if out.returncode == 0 and out.stdout.strip():
            return float(out.stdout.strip())
    except Exception:
        pass
    try:
        import wave
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def multipart(fields: dict, file_field: str, filename: str, filedata: bytes):
    """Build a multipart/form-data body (stdlib only)."""
    boundary = uuid.uuid4().hex
    out = []
    for k, v in fields.items():
        out.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    out.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: audio/wav\r\n\r\n".encode()
    )
    out.append(filedata)
    out.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def bench(name, cfg, audio: Path, seconds: float):
    key = os.environ.get(cfg["key_env"], "").strip()
    if not key:
        return {"provider": name, "skipped": f"no {cfg['key_env']}"}

    body, ctype = multipart(
        {"model": cfg["model"], "response_format": "json"},
        "file", audio.name, audio.read_bytes(),
    )
    req = urllib.request.Request(cfg["url"], data=body, method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", ctype)
    req.add_header("User-Agent", "Mozilla/5.0")

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"provider": name, "model": cfg["model"],
                "error": f"HTTP {e.code}: {e.read().decode('utf-8','replace')[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"provider": name, "model": cfg["model"], "error": f"{type(e).__name__}: {e}"}

    elapsed = time.perf_counter() - t0
    text = (payload.get("text") or "").strip()
    return {
        "provider": name,
        "model": cfg["model"],
        "seconds_taken": round(elapsed, 2),
        "audio_seconds": round(seconds, 1),
        "realtime_factor": round(seconds / elapsed, 1) if elapsed > 0 else None,
        "chars": len(text),
        "text_preview": text[:200],
    }


def main():
    ap = argparse.ArgumentParser(description="Benchmark free speech-to-text APIs")
    ap.add_argument("audio", help="path to a speech file (wav/flac/mp3/ogg…)")
    ap.add_argument("--seconds", type=float, help="audio length if it can't be detected")
    ap.add_argument("providers", nargs="*", help="subset to test")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        sys.exit(f"no such file: {audio}")
    seconds = args.seconds or audio_duration(audio)
    if not seconds:
        sys.exit("could not determine audio length — pass --seconds N")

    load_keys()
    proxy = setup_proxy()
    if proxy:
        print(f"(via proxy {proxy})")
    print(f"audio: {audio.name} — {seconds:.1f}s, {audio.stat().st_size/1024:.0f} KB\n")

    targets = args.providers or list(PROVIDERS)
    results = []
    for n in targets:
        if n not in PROVIDERS:
            print(f"  unknown provider {n}")
            continue
        r = bench(n, PROVIDERS[n], audio, seconds)
        results.append(r)
        if r.get("skipped"):
            print(f"  {n:<12} skipped ({r['skipped']})")
        elif r.get("error"):
            print(f"  {n:<12} ❌ {r['error']}")
        else:
            print(f"  {n:<12} ✅ {r['seconds_taken']}s for {r['audio_seconds']}s audio "
                  f"= {r['realtime_factor']}× realtime, {r['chars']} chars")

    ok = [r for r in results if r.get("realtime_factor")]
    if ok:
        ok.sort(key=lambda r: r["realtime_factor"], reverse=True)
        print("\n| Provider | Model | Time | Realtime factor |")
        print("|---|---|---|---|")
        for r in ok:
            print(f"| {r['provider']} | `{r['model']}` | {r['seconds_taken']}s | "
                  f"**{r['realtime_factor']}×** |")

    out = ROOT / "transcribe_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nraw -> {out.name}")


if __name__ == "__main__":
    raise SystemExit(main())
