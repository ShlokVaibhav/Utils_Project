#!/usr/bin/env python3.12
"""
Fetch YouTube transcripts.

Usage:
  yt_transcript.py [YYYY-MM-DD]                   # all channels in channels.txt, yesterday by default
  yt_transcript.py --url VIDEO_URL                 # single video transcript → stdout
  yt_transcript.py --url CHANNEL_URL [YYYY-MM-DD]  # one channel for a date → daylog

channels.txt lives next to this script:
  Display Name | UCxxxxxxxxxxxxxxxx

Dependencies:
  python3.12 -m pip install --break-system-packages yt-dlp youtube-transcript-api
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import dataclasses
import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SCRIPT_DIR = Path(__file__).parent
CHANNELS_FILE = SCRIPT_DIR / "channels.txt"

ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X) "
    "AppleWebKit/537.36 Chrome/126 Safari/537.36"
)
DEFAULT_CHANNEL_WORKERS = 11
DEFAULT_VIDEO_WORKERS = int(os.environ.get("YT_TRANSCRIPT_VIDEO_WORKERS", "6"))
CAPTION_LANG_PRIORITY = ("en", "en-US", "en-GB")
THREAD_STATE = threading.local()
_COOKIEFILE: str | None = None


# ── data classes ─────────────────────────────────────────────────────────────

@dataclasses.dataclass(slots=True)
class Candidate:
    channel: str
    channel_id: str
    video_id: str
    title: str
    published: dt.datetime
    url: str


@dataclasses.dataclass(slots=True)
class VideoResult:
    candidate: Candidate
    title: str
    duration_seconds: int | None
    duration_text: str
    transcript: str | None = None
    transcript_source: str | None = None
    excluded_reason: str | None = None
    unavailable_reason: str | None = None
    failure_reason: str | None = None
    elapsed_seconds: float = 0.0
    logical_requests: int = 0


@dataclasses.dataclass(slots=True)
class ChannelDiscovery:
    channel: str
    candidates: list[Candidate]
    failures: list[str]
    elapsed_seconds: float
    logical_requests: int


# ── channel list ──────────────────────────────────────────────────────────────

def load_channels(path: Path = CHANNELS_FILE) -> tuple[tuple[str, str], ...]:
    if not path.exists():
        raise SystemExit(f"channels.txt not found: {path}")
    channels = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 1)
        if len(parts) != 2:
            continue
        name, channel_id = parts[0].strip(), parts[1].strip()
        if name and channel_id:
            channels.append((name, channel_id))
    if not channels:
        raise SystemExit(f"No channels found in {path}")
    return tuple(channels)


# ── yt-dlp helpers ───────────────────────────────────────────────────────────

def require_yt_dlp() -> Any:
    try:
        import yt_dlp
    except ImportError as exc:
        raise SystemExit(
            "missing: python3.12 -m pip install --break-system-packages yt-dlp"
        ) from exc
    return yt_dlp


def make_ydl(quiet: bool = True, cookiefile: str | None = None) -> Any:
    yt_dlp = require_yt_dlp()
    browser = os.environ.get("YTDLP_BROWSER", "chrome")
    opts = {
        "quiet": quiet,
        "no_warnings": quiet,
        "skip_download": True,
        "ignoreerrors": False,
        "ignore_no_formats_error": True,
        "format": "bestaudio/best",
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
    }
    if cookiefile:
        opts["cookiefile"] = cookiefile
    else:
        opts["cookiesfrombrowser"] = (browser,)
    return yt_dlp.YoutubeDL(opts)


def thread_ydl() -> Any:
    if not hasattr(THREAD_STATE, "ydl"):
        THREAD_STATE.ydl = make_ydl(cookiefile=_COOKIEFILE)
    return THREAD_STATE.ydl


def export_cookies() -> str | None:
    cookiefile = str(Path.home() / ".yt-cookies.txt")
    try:
        yt_dlp_mod = require_yt_dlp()
        browser = os.environ.get("YTDLP_BROWSER", "chrome")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ignore_no_formats_error": True,
            "cookiesfrombrowser": (browser,),
            "cookiefile": cookiefile,
        }
        with yt_dlp_mod.YoutubeDL(opts) as ydl:
            ydl.extract_info("https://www.youtube.com/watch?v=dQw4w9WgXcQ", download=False)
        p = Path(cookiefile)
        if p.exists() and p.stat().st_size > 0:
            return cookiefile
    except Exception:
        pass
    return None


# ── URL helpers ───────────────────────────────────────────────────────────────

def is_video_url(url: str) -> bool:
    p = urlparse(url)
    if p.hostname in ("youtu.be",):
        return True
    if p.hostname and "youtube" in p.hostname:
        if p.path == "/watch" and "v" in parse_qs(p.query):
            return True
        if re.match(r"^/(embed|shorts|v)/[^/?]+", p.path):
            return True
    return False


def video_id_from_url(url: str) -> str:
    p = urlparse(url)
    if p.hostname in ("youtu.be",):
        return p.path.lstrip("/").split("?")[0]
    if p.path == "/watch":
        return parse_qs(p.query)["v"][0]
    m = re.match(r"^/(embed|shorts|v)/([^/?]+)", p.path)
    if m:
        return m.group(2)
    raise ValueError(f"Cannot extract video ID from: {url}")


def resolve_channel_url(url: str) -> tuple[str, str]:
    """Return (display_name, channel_id) for a channel URL."""
    with make_ydl(cookiefile=_COOKIEFILE) as ydl:
        info = ydl.extract_info(url, download=False, process=False)
    if not info:
        raise SystemExit(f"Could not resolve channel from: {url}")
    channel_id = info.get("channel_id") or info.get("uploader_id", "")
    if not channel_id:
        raise SystemExit(f"No channel_id returned for: {url}")
    name = info.get("channel") or info.get("uploader") or info.get("title") or url
    return str(name), str(channel_id)


# ── transcript extraction ─────────────────────────────────────────────────────

def fetch_url(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def duration_text(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def is_live_or_pending(info: dict[str, Any]) -> str | None:
    status = info.get("live_status")
    if info.get("is_live") or status in {"is_live", "post_live"}:
        return "live stream"
    if status in {"is_upcoming", "is_premiere"}:
        return "premiere not yet aired"
    ts = info.get("release_timestamp")
    if isinstance(ts, (int, float)) and ts > time.time():
        return "premiere not yet aired"
    return None


def choose_caption(info: dict[str, Any]) -> tuple[str, str] | None:
    subtitles = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}
    for kind, pool in (("manual", subtitles), ("auto", automatic)):
        for lang in CAPTION_LANG_PRIORITY:
            if lang in pool and pool[lang]:
                return lang, kind
    for kind, pool in (("manual", subtitles), ("auto", automatic)):
        for lang, tracks in pool.items():
            if tracks:
                return lang, kind
    return None


def best_track(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not tracks:
        return None
    for ext in ("json3", "srv3", "vtt", "ttml", "srv2", "srv1"):
        for t in tracks:
            if t.get("ext") == ext and t.get("url"):
                return t
    return next((t for t in tracks if t.get("url")), None)


def parse_json3(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ""
    pieces = [
        seg.get("utf8", "")
        for ev in data.get("events", [])
        for seg in (ev.get("segs") or [])
    ]
    return normalize(" ".join(pieces))


def parse_xml_caption(text: str) -> str:
    try:
        root = ET.fromstring(text)
        return normalize(" ".join(n.text for n in root.iter() if n.text))
    except ET.ParseError:
        return normalize(re.sub(r"<[^>]+>", " ", text))


def parse_vtt(text: str) -> str:
    pieces = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or s.startswith(("Kind:", "Language:")) or "-->" in s:
            continue
        if re.fullmatch(r"\d+", s):
            continue
        pieces.append(re.sub(r"<[^>]+>", "", s))
    return normalize(" ".join(pieces))


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_caption_with_ytdlp(ydl: Any, url: str) -> str:
    resp = ydl.urlopen(url)
    text = resp.read().decode("utf-8", errors="replace")
    ct = resp.headers.get("content-type", "")
    stripped = text.lstrip()
    # Reject HTML responses — redirected to YouTube homepage, not a caption file.
    if "text/html" in ct or stripped.startswith(("<!DOCTYPE", "<html", "window.", "var ")):
        return ""
    if "json" in ct or stripped.startswith("{"):
        result = parse_json3(text)
        return result if len(result) > 50 else ""
    if "<transcript" in text or "<text" in text:
        return parse_xml_caption(text)
    if stripped.startswith("WEBVTT") or "\n-->" in text:
        return parse_vtt(text)
    return ""


def fallback_transcript_api(video_id: str) -> tuple[str, str] | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    api = YouTubeTranscriptApi()
    try:
        t = api.fetch(video_id, languages=CAPTION_LANG_PRIORITY)
        return _api_text(t), "youtube-transcript-api en"
    except Exception:
        pass
    try:
        for item in api.list(video_id):
            try:
                return _api_text(item.fetch()), f"youtube-transcript-api {item.language_code}"
            except Exception:
                continue
    except Exception:
        pass
    return None


def _api_text(transcript: Any) -> str:
    return normalize(" ".join(getattr(s, "text", "").replace("\n", " ") for s in transcript))


def process_video(candidate: Candidate) -> VideoResult:
    started = time.perf_counter()
    result = VideoResult(
        candidate=candidate,
        title=candidate.title,
        duration_seconds=None,
        duration_text="unknown",
    )
    try:
        ydl = thread_ydl()
        result.logical_requests += 1
        info = ydl.extract_info(candidate.url, download=False)
        if not info:
            result.failure_reason = "yt-dlp returned no metadata"
            return result
        result.title = info.get("title") or candidate.title
        dur = info.get("duration")
        result.duration_seconds = int(dur) if isinstance(dur, (int, float)) else None
        result.duration_text = duration_text(result.duration_seconds)
        if result.duration_seconds is not None and result.duration_seconds < 60:
            result.excluded_reason = "Shorts/duration < 60s"
            return result
        live = is_live_or_pending(info)
        if live:
            result.excluded_reason = live
            return result
        cap = choose_caption(info)
        if cap:
            lang, kind = cap
            pool = info.get("subtitles" if kind == "manual" else "automatic_captions") or {}
            track = best_track(pool.get(lang, []))
            if track and track.get("url"):
                result.logical_requests += 1
                result.transcript = fetch_caption_with_ytdlp(ydl, track["url"])
                result.transcript_source = f"yt-dlp {kind} {lang}"
                if result.transcript:
                    return result
        fb = fallback_transcript_api(candidate.video_id)
        if fb:
            result.logical_requests += 2
            result.transcript, result.transcript_source = fb
            return result
        result.unavailable_reason = "no usable captions found"
    except Exception as exc:
        fb = fallback_transcript_api(candidate.video_id)
        if fb:
            result.logical_requests += 2
            result.transcript, result.transcript_source = fb
        else:
            result.failure_reason = f"{type(exc).__name__}: {str(exc).splitlines()[0][:240]}"
    finally:
        result.elapsed_seconds = time.perf_counter() - started
    return result


# ── discovery ─────────────────────────────────────────────────────────────────

def discover_channel(channel: str, channel_id: str, target_date: dt.date) -> ChannelDiscovery:
    started = time.perf_counter()
    candidates: list[Candidate] = []
    failures: list[str] = []
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        root = ET.fromstring(fetch_url(feed_url))
        for entry in root.findall("atom:entry", ATOM_NS):
            vid = entry.findtext("yt:videoId", namespaces=ATOM_NS)
            title = entry.findtext("atom:title", default="", namespaces=ATOM_NS)
            pub_text = entry.findtext("atom:published", namespaces=ATOM_NS)
            if not vid or not pub_text:
                continue
            pub = dt.datetime.fromisoformat(pub_text.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
            if pub.date() != target_date:
                continue
            candidates.append(Candidate(
                channel=channel, channel_id=channel_id, video_id=vid,
                title=title, published=pub,
                url=f"https://www.youtube.com/watch?v={vid}",
            ))
    except (ET.ParseError, urllib.error.URLError, TimeoutError) as exc:
        failures.append(f"RSS failed: {type(exc).__name__}: {exc}")
    return ChannelDiscovery(
        channel=channel, candidates=candidates, failures=failures,
        elapsed_seconds=time.perf_counter() - started, logical_requests=1,
    )


# ── metrics ───────────────────────────────────────────────────────────────────

def compute_reward(
    fetched: int, failures: int, n_channels: int,
    same_day_candidates: int, logical_requests: int,
    useful_elapsed: float, wall_seconds: float, video_workers: int,
) -> tuple[float, float, float, float]:
    total = fetched + failures
    F = failures / total if total else 0.0
    capacity = max(1, video_workers) * max(wall_seconds, 1e-9)
    eta = min(1.0, useful_elapsed / capacity)
    r_min = n_channels + 2 * max(1, same_day_candidates)
    rho = logical_requests / r_min
    R = 0.5 * (1 - F) + 0.3 * min(eta, 1.0) + 0.2 * (1 - min(max(rho - 1.0, 0.0), 1.0))
    return F, eta, rho, R


# ── rendering ─────────────────────────────────────────────────────────────────

def render_document(
    target_date: dt.date,
    channels: tuple[tuple[str, str], ...],
    discoveries: list[ChannelDiscovery],
    video_results: list[VideoResult],
    metrics: dict[str, Any],
) -> str:
    by_channel: dict[str, list[VideoResult]] = {name: [] for name, _ in channels}
    excluded: list[VideoResult] = []
    unavailable: list[VideoResult] = []
    failures: list[str] = []

    for d in discoveries:
        failures.extend(f"{d.channel}: {f}" for f in d.failures)
    for r in video_results:
        if r.transcript:
            by_channel.setdefault(r.candidate.channel, []).append(r)
        elif r.excluded_reason:
            excluded.append(r)
        elif r.unavailable_reason:
            unavailable.append(r)
        elif r.failure_reason:
            failures.append(f"{r.candidate.channel}: {r.title} | {r.candidate.url} | {r.failure_reason}")

    lines: list[str] = []
    for channel, _ in channels:
        lines.append(f"# {channel} — {target_date.isoformat()}")
        for r in sorted(by_channel.get(channel, []), key=lambda x: x.candidate.published):
            lines += ["", f"## {r.title} | {r.candidate.url} | {r.duration_text}", "",
                      textwrap.fill(r.transcript or "", width=100,
                                    break_long_words=False, break_on_hyphens=False),
                      "", "---"]
        if not by_channel.get(channel):
            lines.append("\n_No eligible transcript fetched for this UTC date._")
        lines.append("")

    lines += [
        "# RUN REPORT",
        f"F = {metrics['F']:.3f}   η = {metrics['eta']:.3f}   "
        f"ρ = {metrics['rho']:.3f}   T_wall = {metrics['T_wall']:.2f} s   R = {metrics['R']:.3f}",
        "",
        f"- Same-day candidates = {metrics['candidates']}",
        f"- Fetched = {metrics['fetched']}   Unavailable = {len(unavailable)}"
        f"   Failures = {len(failures)}   Excluded = {len(excluded)}",
        f"- Logical requests = {metrics['logical_requests']}   R_min = {metrics['r_min']}",
        "",
        "## UNAVAILABLE",
    ]
    lines += [f"- {r.candidate.channel}: {r.title} | {r.candidate.url} | {r.unavailable_reason}"
              for r in unavailable] or ["- None"]
    lines += ["", "## FAILURES"]
    lines += [f"- {f}" for f in failures] or ["- None"]
    if excluded:
        lines += ["", "## EXCLUDED"]
        lines += [f"- {r.candidate.channel}: {r.title} | {r.candidate.url} | {r.excluded_reason}"
                  for r in excluded]
    return "\n".join(lines) + "\n"


# ── modes ─────────────────────────────────────────────────────────────────────

def run_digest(channels: tuple[tuple[str, str], ...], target_date: dt.date) -> int:
    n_ch = len(channels)
    ch_workers = min(DEFAULT_CHANNEL_WORKERS, n_ch)
    started = time.perf_counter()

    with futures.ThreadPoolExecutor(max_workers=ch_workers) as ex:
        disc_futs = [ex.submit(discover_channel, ch, cid, target_date) for ch, cid in channels]
        discoveries = [f.result() for f in futures.as_completed(disc_futs)]
    ch_order = [ch for ch, _ in channels]
    discoveries.sort(key=lambda d: ch_order.index(d.channel))

    seen: set[str] = set()
    candidates: list[Candidate] = []
    for d in discoveries:
        for c in d.candidates:
            if c.video_id not in seen:
                seen.add(c.video_id)
                candidates.append(c)

    v_workers = min(DEFAULT_VIDEO_WORKERS, max(1, len(candidates)))
    with futures.ThreadPoolExecutor(max_workers=v_workers) as ex:
        vid_futs = [ex.submit(process_video, c) for c in candidates]
        results = [f.result() for f in futures.as_completed(vid_futs)]

    wall = time.perf_counter() - started
    fetched = sum(1 for r in results if r.transcript)
    fail_count = sum(1 for r in results if r.failure_reason)
    log_reqs = sum(d.logical_requests for d in discoveries) + sum(r.logical_requests for r in results)
    useful = sum(r.elapsed_seconds for r in results)
    F, eta, rho, R = compute_reward(
        fetched=fetched, failures=fail_count, n_channels=n_ch,
        same_day_candidates=len(candidates), logical_requests=log_reqs,
        useful_elapsed=useful, wall_seconds=wall, video_workers=v_workers,
    )
    r_min = n_ch + 2 * max(1, len(candidates))
    metrics = dict(F=F, eta=eta, rho=rho, T_wall=wall, R=R,
                   candidates=len(candidates), fetched=fetched,
                   logical_requests=log_reqs, r_min=r_min)

    dest = Path.home() / "daylog" / f"{target_date.isoformat()}-YT.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_document(target_date, channels, discoveries, results, metrics), encoding="utf-8")
    print(dest)
    print(f"F={F:.3f} η={eta:.3f} ρ={rho:.3f} T_wall={wall:.2f}s R={R:.3f}")
    return 0


def run_single_video(url: str) -> int:
    vid = video_id_from_url(url)
    candidate = Candidate(
        channel="", channel_id="", video_id=vid, title=vid,
        published=dt.datetime.now(dt.timezone.utc), url=url,
    )
    result = process_video(candidate)
    if result.transcript:
        print(result.transcript)
        return 0
    if result.excluded_reason:
        raise SystemExit(f"Excluded: {result.excluded_reason}")
    if result.unavailable_reason:
        raise SystemExit(f"Unavailable: {result.unavailable_reason}")
    raise SystemExit(f"Failed: {result.failure_reason}")


def run_single_channel(url: str, target_date: dt.date) -> int:
    print(f"Resolving channel from {url} …", file=sys.stderr)
    name, channel_id = resolve_channel_url(url)
    print(f"  → {name} ({channel_id})", file=sys.stderr)
    return run_digest(((name, channel_id),), target_date)


# ── entry point ───────────────────────────────────────────────────────────────

def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch YouTube transcripts for configured channels or a URL.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  yt_transcript.py                          # yesterday, all channels\n"
            "  yt_transcript.py 2026-06-27               # specific date, all channels\n"
            "  yt_transcript.py --url https://youtu.be/ID  # single video → stdout\n"
            "  yt_transcript.py --url https://youtube.com/@Handle 2026-06-27\n"
        ),
    )
    p.add_argument("date", nargs="?", help="YYYY-MM-DD (default: yesterday UTC)")
    p.add_argument("--url", metavar="URL", help="video or channel URL")
    return p.parse_args(argv[1:])


def resolve_date(date_str: str | None) -> dt.date:
    if date_str is None:
        return dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError:
        raise SystemExit(f"Invalid date: {date_str!r} — use YYYY-MM-DD")


def main(argv: list[str]) -> int:
    global _COOKIEFILE
    args = parse_args(argv)
    target_date = resolve_date(args.date)

    _COOKIEFILE = export_cookies()

    if args.url:
        if is_video_url(args.url):
            return run_single_video(args.url)
        else:
            return run_single_channel(args.url, target_date)
    else:
        channels = load_channels()
        return run_digest(channels, target_date)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
