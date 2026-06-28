# Utils_Projects

Personal utility scripts. Each tool is standalone — no shared framework.

---

## yt_transcript.py

Fetches YouTube transcripts for a configured list of channels and compiles them into a daily Markdown digest. Also supports one-off fetches by video or channel URL.

### Dependencies

```bash
python3.12 -m pip install --break-system-packages yt-dlp youtube-transcript-api
```

### Usage

```bash
# All channels in channels.txt, yesterday UTC
python3.12 yt_transcript.py

# Specific date
python3.12 yt_transcript.py 2026-06-27

# Single video — transcript printed to stdout
python3.12 yt_transcript.py --url https://youtu.be/VIDEO_ID

# Single channel for a date — appended to reading log
python3.12 yt_transcript.py --url https://www.youtube.com/@Handle 2026-06-27
```

Output goes to `~/daylog/YYYY-MM-DD-YT.md`.

### Adding or editing channels

Edit `channels.txt` in this directory. Format:

```
# Display Name | Channel ID
Patrick Boyle | UCASM0cgfkJxQ1ICmRilfHLw
```

Lines starting with `#` are comments. Channel IDs can be found in the channel's RSS feed URL:
`https://www.youtube.com/feeds/videos.xml?channel_id=UC...`

### How it works

1. Reads `channels.txt` for the channel list
2. Exports your Chrome cookies to `~/.yt-cookies.txt` (one keychain prompt)
3. Fetches each channel's RSS feed in parallel to find videos published on the target date
4. For each video: extracts captions via yt-dlp (primary), falls back to youtube-transcript-api
5. Excludes Shorts (< 60s) and live streams
6. Writes a structured Markdown file with a run report at the end

### Run report metrics

Each output file ends with:

```
F = 0.000   η = 0.861   ρ = 1.257   T_wall = 18.54 s   R = 0.907
```

| Metric | Meaning | Target |
|---|---|---|
| F | Failure rate — fraction of fetchable transcripts that failed | < 0.02 |
| η | Parallelism efficiency — how well workers stayed busy | > 0.70 |
| ρ | Request overhead — actual requests / minimum possible | < 1.6 |
| R | Composite reward (0–1) | > 0.85 |

### IP blocks

YouTube rate-limits transcript fetches by IP. If you see `IpBlocked` errors:
- Connect to a phone hotspot and re-run — fresh IP, works immediately
- The block usually clears within 24 hours on a residential connection
- Do not run aggressive multi-request strategies (Innertube etc.) from the same IP

### Environment variables

| Variable | Default | Effect |
|---|---|---|
| `YTDLP_BROWSER` | `chrome` | Browser to read cookies from (`firefox`, `safari`, etc.) |
| `YT_TRANSCRIPT_VIDEO_WORKERS` | `6` | Parallel video fetch workers |
