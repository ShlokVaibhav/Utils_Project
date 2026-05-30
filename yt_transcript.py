#!/usr/bin/env python3
"""Usage: yt_transcript.py <youtube_url> [output_dir]"""
import sys
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from youtube_transcript_api import YouTubeTranscriptApi


def video_id(url: str) -> str:
    u = urlparse(url)
    if u.hostname in ("youtu.be",):
        return u.path.lstrip("/")
    if u.hostname and "youtube" in u.hostname:
        if u.path == "/watch":
            return parse_qs(u.query)["v"][0]
        m = re.match(r"^/(embed|shorts|v)/([^/?]+)", u.path)
        if m:
            return m.group(2)
    raise ValueError(f"Could not extract video id from: {url}")


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: yt_transcript.py <youtube_url> [output_dir]")
    url = sys.argv[1]
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    vid = video_id(url)
    transcript = YouTubeTranscriptApi().fetch(vid)
    text = "\n".join(snip.text for snip in transcript)

    out_path = out_dir / f"{vid}.txt"
    out_path.write_text(text, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
