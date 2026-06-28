# AGENTS.md — Context for LLM agents working on Utils_Projects

## Repo layout

```
Utils_Projects/
├── yt_transcript.py   # main script
├── channels.txt       # channel list (editable — this is the config)
├── README.md
└── AGENTS.md
```

## yt_transcript.py

### What it does

Fetches YouTube transcripts for a date and writes them to `~/daylog/YYYY-MM-DD-YT.md`.
Three modes depending on CLI args (see below).

### How to invoke

```bash
python3.12 yt_transcript.py [YYYY-MM-DD]                   # all channels, date optional
python3.12 yt_transcript.py --url https://youtu.be/ID       # single video → stdout
python3.12 yt_transcript.py --url https://youtube.com/@H [date]  # single channel → reading log
```

Default date: yesterday UTC. Never guess a date — compute it from `datetime.date.today() - timedelta(days=1)` in UTC.

### Dependencies (must be present before running)

```bash
python3.12 -m pip install --break-system-packages yt-dlp youtube-transcript-api
python3.12 -c "import yt_dlp; import youtube_transcript_api; print('ok')"
```

If either import fails, install before proceeding. Do not use `pip` (wired to Python 3.9 on this machine) — always use `python3.12 -m pip`.

### Output

- Multi-channel / single-channel mode: `~/daylog/YYYY-MM-DD-YT.md`
- Single video mode: stdout only, no file written
- Final line of stdout: `F=0.000 η=0.861 ρ=1.257 T_wall=18.54s R=0.907`

### Metrics (parse from stdout after a run)

```
R = 0.5*(1-F) + 0.3*η + 0.2*(1 - clamp(ρ-1, 0, 1))
```

| Symbol | Formula | Target |
|---|---|---|
| F | failed_transcripts / (fetched + failed) | < 0.02 |
| η | Σ(T_i per video) / (n_workers × T_wall) | > 0.70 |
| ρ | actual_requests / (n_channels + 2×n_videos) | < 1.6 |
| R | composite reward | > 0.85 |

A run with F > 0 or R < 0.85 should NOT be marked complete.

### Failure modes and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `IpBlocked` from youtube-transcript-api | IP rate-limited by YouTube | Switch to phone hotspot; block clears in ~24h |
| `HTTP 429` fetching caption URL | Same IP block, yt-dlp path | Same fix |
| `ModuleNotFoundError: yt_dlp` | Installed for wrong Python | `python3.12 -m pip install --break-system-packages yt-dlp` |
| `TypeError: unexpected keyword argument 'cookies'` | youtube-transcript-api v1.2.4 has no `cookies=` param | Use `http_client=` with a requests.Session, or omit |
| Keychain prompt loop | Multiple threads requesting Chrome cookies simultaneously | Script exports cookies once in main thread to `~/.yt-cookies.txt`; threads reuse that file |
| F=1.000 with ρ<1.0 | Cookie export failed silently, threads fell back to browser access and were denied | Check `~/.yt-cookies.txt` exists and is non-empty; re-run on fresh IP |
| `was_live` videos missing | Correctly excluded — completed livestream VODs are NOT excluded (only `is_live`, `post_live`) | Expected behavior |

### Internal architecture

```
main()
  │
  ├── export_cookies()          # one keychain prompt, writes ~/.yt-cookies.txt
  │
  ├── [--url video]  → run_single_video()
  │     └── process_video(synthetic_candidate)  → stdout
  │
  ├── [--url channel] → run_single_channel()
  │     └── resolve_channel_url()  via yt-dlp extract_info(process=False)
  │     └── run_digest(single channel tuple, date)
  │
  └── [default]  → load_channels() → run_digest(all channels, date)
        │
        ├── ThreadPoolExecutor(n_channels workers)
        │     └── discover_channel() per channel  ← RSS feed, no auth
        │
        └── ThreadPoolExecutor(min(6, n_videos) workers)
              └── process_video() per candidate
                    ├── yt-dlp extract_info()     [primary, 1 request]
                    ├── fetch caption URL via ydl  [if captions found, 1 request]
                    └── fallback_transcript_api()  [if yt-dlp fails, 2 requests]
```

### channels.txt format

```
# comment
Display Name | UCxxxxxxxxxxxxxxxxxx
```

- One channel per line
- Pipe-separated: name on left, channel ID on right
- Lines starting with `#` are ignored
- File lives next to the script (`Path(__file__).parent / "channels.txt"`)
- To add a channel: append a line. To disable: prefix with `#`.

### Confirmed channel IDs (as of June 2026)

```
Patrick Boyle         UCASM0cgfkJxQ1ICmRilfHLw   @PBoyle
Vox                   UCLXo7UDZvByw2ixzpQCufnA
DW Documentary        UCW39zufHfsuGgpLviKh297Q
Slice Full Doc        UCGDXj3vSgJ8MCbzbb_C9thA
The Information       UCoKqUtcUtf8QPb0GWxe5e7Q
Y Combinator          UCcefcZRL2oaA_uBNeo5UOWg
DW History & Culture  UCXD5-f9urX1Foas68AL_HHQ
YC Root Access        UCxIJaCMEptJjxmmQgGFsnCg
DW Planet A           UCb72Gn5LXaLEcsOuPKGfQOg
The Wall Street Journal UCK7tptUDHh-RYDsdxO1-5QQ
Standard Capital      UClhrjxsv4Dscc-um1UequTw
```

### Key constraints for this machine

- Python: use `python3.12` — `python3` resolves to 3.14 which has a broken pyexpat on this machine
- pip: use `python3.12 -m pip`, never bare `pip` (wired to 3.9)
- Cookie browser default: `chrome`; override with `YTDLP_BROWSER=firefox` if Chrome is closed
- Output directory: `~/daylog/` — created automatically if missing, files named `YYYY-MM-DD-YT.md`
- Cookie cache: `~/.yt-cookies.txt` — safe to delete and regenerate; do not commit to git

### What not to do

- Do not use the InnerTube API or aggressive scraping strategies — triggers IP blocks
- Do not run Whisper transcription unless all other methods fail (dominates ρ and T_wall)
- Do not mark a run complete if F > 0.02 or R < 0.85
- Do not commit `~/.yt-cookies.txt` or `~/.config/` contents to git
- Do not use `python3` directly — use `python3.12`
