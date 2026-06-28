---
name: yt-sv
description: Run and diagnose Shlok's local YouTube transcript pipeline in /Users/shlok/Documents/Repos/Utils_Projects. Use when the user asks to fetch YouTube transcripts, build the daily reading digest, get a single video transcript, fetch one channel's videos for a date, inspect or update the configured channel list, read a generated ~/daylog/reading/YYYY-MM-DD.md digest, or interpret the pipeline metrics F, η, ρ, T_wall, and R.
---

# yt-sv

Use the local YouTube transcript pipeline at:

`/Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py`

Read `/Users/shlok/Documents/Repos/Utils_Projects/AGENTS.md` before running or editing the pipeline if you have not already read it this session. Treat that file as authoritative for current script behavior, environment constraints, metrics, channel IDs, and failure handling.

## Hard Rules

- Use `python3.12`, never `python3`; this machine's `python3` resolves to 3.14 and has broken `pyexpat` for this workflow.
- Use `python3.12 -m pip ...`, never bare `pip` or `pip3`.
- Do not use InnerTube API experiments or aggressive scraping; they trigger YouTube IP blocks.
- Do not run Whisper unless every transcript method has failed and the user explicitly accepts the cost and time.
- Do not commit `~/.yt-cookies.txt`, browser cookie exports, captures, or daylog outputs.
- Do not mark a transcript run complete if `F > 0.02` or `R < 0.85`.

## Dependency Check

Before running the pipeline, verify dependencies for Python 3.12:

```bash
python3.12 -c "import yt_dlp; import youtube_transcript_api; print('ok')"
```

If imports fail, install with:

```bash
python3.12 -m pip install --break-system-packages yt-dlp youtube-transcript-api
```

## Commands

Run from `/Users/shlok/Documents/Repos/Utils_Projects` or use the absolute script path.

| User request | Command |
|---|---|
| Yesterday's digest for all configured channels | `python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py` |
| Digest for a specific UTC date | `python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py YYYY-MM-DD` |
| Single video transcript to stdout | `python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py --url URL` |
| Single channel digest for a date | `python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py --url CHANNEL_URL YYYY-MM-DD` |

Default date is yesterday UTC. When the user gives relative dates, state the exact UTC date you are using.

## Outputs

- Multi-channel and single-channel digest output: `~/daylog/reading/YYYY-MM-DD.md`
- Single-video mode: stdout only, no file written
- Channel config: `/Users/shlok/Documents/Repos/Utils_Projects/channels.txt`
- Cookie cache: `~/.yt-cookies.txt`; safe to delete and regenerate, never commit

## After Every Run

Parse the final stdout metrics line, for example:

```text
F=0.000 η=0.861 ρ=1.257 T_wall=18.54s R=0.907
```

Report a compact table:

| Metric | Target | Completion gate |
|---|---|---|
| F | `< 0.02` | lower is better |
| η | `> 0.70` | higher is better |
| ρ | `< 1.60` | lower is better |
| R | `> 0.85` | higher is better |

Use this reward formula when checking results:

```text
R = 0.5*(1-F) + 0.3*η + 0.2*(1 - clamp(ρ-1, 0, 1))
```

Use the corrected request floor for ρ:

```text
R_min = n_channels + 2*n_videos
ρ = actual_requests / R_min
```

If any gate fails, continue diagnosis instead of presenting the run as complete.

## Common Tasks

### Show the channel list

Read `/Users/shlok/Documents/Repos/Utils_Projects/channels.txt` and display non-comment entries.

### Add a channel

Resolve the channel ID, then append this format to `channels.txt`:

```text
Channel Name | UCxxxxxxxxxxxxxxxxxx
```

Prefer `yt-dlp` or YouTube RSS/channel metadata for resolution. Do not bulk-generate or guess IDs. Confirm the exact added line.

### Show a reading digest

Read `~/daylog/reading/YYYY-MM-DD.md`. Summarize by channel and video title, with 2-3 bullets per video. Flag items relevant to CRPA, RF, ADC, SerDes, BiCMOS, DSP, RTL, or startup/company strategy.

## Failure Handling

| Symptom | Likely cause | Action |
|---|---|---|
| `IpBlocked` or `HTTP 429` | YouTube rate-limited current IP | Tell the user to connect to phone hotspot and re-run; block usually clears in about 24 hours |
| `ModuleNotFoundError: yt_dlp` | Dependency installed for wrong Python | Run the Python 3.12 install command above |
| `TypeError: unexpected keyword argument` | Bad `YouTubeTranscriptApi()` kwarg from a prior edit | Remove unsupported kwargs such as `cookies=`; use `http_client=` with a `requests.Session` or omit |
| Keychain prompt loop | Threads are reading browser cookies independently | Verify cookie export happens once in `main()` before thread pools and workers reuse `~/.yt-cookies.txt` |
| `F=1.000` with implausibly low ρ | Cookie export failed or transcript fetches all failed | Check `~/.yt-cookies.txt` exists and is non-empty; re-run on hotspot |
| Completed livestream VOD appears | Expected if it is not currently live/post-live | Exclude only active live streams and pending premieres; do not exclude normal VODs solely because they were live |

## Environment Notes

- Default browser for cookies: Chrome; override with `YTDLP_BROWSER=firefox` or another yt-dlp-supported browser.
- Video worker count is controlled by `YT_TRANSCRIPT_VIDEO_WORKERS`; default is 6.
- Output directory `~/daylog/reading/` is created automatically by the script.
