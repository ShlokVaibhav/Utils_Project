# yt-sv — YouTube transcript skill

You are interfacing with the YouTube transcript pipeline at:
`/Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py`

Full context for this script is in:
`/Users/shlok/Documents/Repos/Utils_Projects/AGENTS.md`

Read AGENTS.md before doing anything if you have not already done so this session.

---

## Interpreter and invocation rules

- Always use `python3.12` — never `python3` (resolves to 3.14, broken pyexpat on this machine)
- Script path: `/Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py`
- Channels config: `/Users/shlok/Documents/Repos/Utils_Projects/channels.txt`
- Output lands in: `~/daylog/YYYY-MM-DD-YT.md`

---

## What the user might say and what to do

**"fetch today's / yesterday's transcripts"**
```bash
python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py
```

**"fetch transcripts for [date]"**
```bash
python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py YYYY-MM-DD
```

**"get transcript for [video URL or YouTube link]"**
```bash
python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py --url URL
```
Transcript prints to stdout. Show it to the user or pipe it as needed.

**"fetch transcripts for [channel name or URL]" (not in channels.txt)**
```bash
python3.12 /Users/shlok/Documents/Repos/Utils_Projects/yt_transcript.py --url CHANNEL_URL [date]
```

**"add [channel] to my list"**
Resolve the channel ID (use yt-dlp or the RSS feed trick), then append to channels.txt:
```
Channel Name  | UCxxxxxxxxxxxxxxxxxx
```
Confirm the addition to the user.

**"what channels am I subscribed to" / "show my channel list"**
Read and display `channels.txt`, skipping comment lines.

**"show me yesterday's digest" / "open the reading log"**
Read `~/daylog/YYYY-MM-DD-YT.md` and summarise: channels present, video count, any failures.

---

## After every run

Parse the metrics line from stdout:
```
F=0.000 η=0.861 ρ=1.257 T_wall=18.54s R=0.907
```

Report back as a compact table. Flag if any target is missed:

| Metric | Value | Target | Status |
|---|---|---|---|
| F | … | < 0.02 | ✅ / ❌ |
| η | … | > 0.70 | ✅ / ❌ |
| ρ | … | < 1.60 | ✅ / ❌ |
| R | … | > 0.85 | ✅ / ❌ |

Do NOT mark the run complete if F > 0.02 or R < 0.85.

---

## Failure handling

**`IpBlocked` or `HTTP 429`**
Tell the user: "Your home IP is rate-limited by YouTube. Connect to your phone's hotspot and re-run — the script will work on a fresh IP. The block clears on its own within ~24 hours."

**`ModuleNotFoundError: yt_dlp`**
Run: `python3.12 -m pip install --break-system-packages yt-dlp youtube-transcript-api`
Then retry.

**`TypeError: unexpected keyword argument`**
The script has a bug introduced by a prior edit. Read `yt_transcript.py` around the `YouTubeTranscriptApi()` call and remove any unsupported kwargs (`cookies=` is not valid in v1.2.4 — use `http_client=` with a requests.Session or omit entirely).

**Keychain prompt loop**
The cookie export in `main()` is firing per-thread instead of once. Verify `export_cookies()` is called in `main()` before the thread pool is created and that `_COOKIEFILE` is set globally before workers start.

**F=1.000 with ρ < 1.0**
Cookie export failed silently. Check `~/.yt-cookies.txt` exists and is non-empty. Re-run on hotspot.

---

## What NOT to do

- Do not use InnerTube API or aggressive scraping — triggers IP blocks
- Do not run Whisper unless everything else fails
- Do not use bare `pip` or `python3`
- Do not commit `~/.yt-cookies.txt` to git
- Do not mark a run complete if targets are missed
