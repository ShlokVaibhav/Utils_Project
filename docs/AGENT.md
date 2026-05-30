# AGENT.md — session handoff

## Project
`Utils_Projects/` — a grab-bag of small standalone utility scripts. Currently holds one tool.

## What exists

### `yt_transcript.py` — YouTube transcript downloader
Minimal CLI that fetches a video's transcript (no video download) and writes it to a text file.

**Usage:**
```
python3 yt_transcript.py <youtube_url> [output_dir]
```
- `output_dir` optional; defaults to the current working directory.
- Output filename is `<videoid>.txt`, one transcript line per row.

**How it works:**
- `video_id()` parses the 11-char video ID from `youtube.com/watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/v/` URL forms.
- Uses the `youtube-transcript-api` package: `YouTubeTranscriptApi().fetch(vid)`, then joins `snip.text` over the returned snippets.

**Dependency:**
- `youtube-transcript-api` (installed v1.2.4).
- IMPORTANT environment quirk on this machine: `pip3` maps to **Python 3.9**, but `python3` resolves to **Python 3.14** (`/Library/Frameworks/Python.framework/Versions/3.14`). Always install with `python3 -m pip install --user <pkg>` so the dep lands in the interpreter that runs the script. Installing via bare `pip3` will NOT be visible to `python3`.

**Verified:** smoke-tested against `dQw4w9WgXcQ`; produced an 89-line transcript. Test artifact was cleaned up.

## API notes (youtube-transcript-api v1.x)
- v1.x is instance-based: `YouTubeTranscriptApi().fetch(video_id)` returns an iterable of snippet objects with a `.text` attribute (not the old static `get_transcript()` returning dicts). Don't downgrade to the pre-1.0 static API.

## Open / possible next steps (none requested yet)
- No language selection (currently grabs the default transcript). Could add a `--lang` arg.
- No timestamp output option (currently text-only). Snippets carry `.start` / `.duration` if SRT/VTT output is wanted.
- No error handling for videos without transcripts / disabled captions — would raise from the library.
- `readme.md` at the repo root is empty.
