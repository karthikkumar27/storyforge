# StoryForge

**An autonomous AI pipeline that turns a one-line story idea into a published YouTube video — from a single API call.**

StoryForge reads a story brief from a Google Sheet, writes the script with Claude, generates reference images and video shots with image/video models, stitches everything together with `ffmpeg`, and uploads the finished video to YouTube. No human in the loop between `POST /run` and a live video.

```
Story idea  ──►  Script  ──►  Images  ──►  Video shots  ──►  Stitch  ──►  Upload  ──►  Live on YouTube
  (Sheet)      (Claude)    (GPT Image)    (Seedance)      (ffmpeg)     (YouTube API)
```

> Personal R&D project. It currently drives a flagship 200-episode animated series (*The Chronicle of Zenith*) end-to-end for roughly **$1.10 per episode**.

---

## What it does

- **Idea → published video, fully automated.** One `POST /run` call produces a complete, uploaded YouTube video.
- **Story-aware scripting.** Claude generates the brief and a per-shot storyboard, guided by a library of loadable "skills" (storytelling craft, episode architecture, character consistency, camera/lighting direction).
- **Character consistency across a long-running series.** Locked appearance paragraphs and reference images fight visual drift across hundreds of episodes.
- **7 content presets** — swap genre, voice, visual style, and story mode with one env var (`CONTENT_PRESET`).
- **Provider-agnostic media stack.** Image and video providers are pluggable via env vars.
- **Title/end cards** pre-rendered once (PNG + MP3 → MP4) and cached by content hash.

## Architecture

```
Google Sheet (brief)
    │
    ▼
Brief Generator (Claude) ──► Script Generator (Claude) ──► Image Generator (GPT Image 2)
                                       │                              │
                                       ▼                              ▼
                              Video Producer (Seedance) ◄──── reference image (first frame)
                                       │
                                       ▼
                              ffmpeg stitch (+ optional title/end cards)
                                       │
                                       ▼
                              Audio Mixer (ElevenLabs — skipped when the video model has native audio)
                                       │
                                       ▼
                              YouTube Uploader
                                       │
                                       ▼
                              Sheet status → done + youtube_url
```

## Provider stack

| Component | Provider | Model |
|-----------|----------|-------|
| LLM (briefs + scripts) | Anthropic | `claude-sonnet-4-6` |
| Reference images | Atlas Cloud (proxies OpenAI) | `gpt-image-2` |
| Video shots | Atlas Cloud (proxies BytePlus) | `seedance-v1.5-pro` (image-to-video + text-to-video) |
| TTS / BGM (optional) | ElevenLabs | `eleven_multilingual_v2` |
| Sheet I/O | Google Sheets API | `gspread` |
| Upload | YouTube Data API v3 | OAuth2 |

Providers are selected with `VIDEO_PROVIDER` / `IMAGE_PROVIDER` (e.g. `atlas`, `seedance`, `seedream`, `kling`).

## Content presets

| Preset | Theme | Mode |
|--------|-------|------|
| `preset-1` | Dark cinematic sci-fi | Series (3 parts) |
| `preset-2` | Shoujo anime comedy | Standalone |
| `preset-3` | Fantasy / mythology | Series (3 parts) |
| `preset-4`–`6` | Kids content (rhymes, adventures, edutainment) | Ongoing series |
| `preset-7` | **The Chronicle of Zenith** — 200-episode continuous saga | Ongoing series |

## Quick start

```bash
# 1. Clone
git clone https://github.com/karthikkumar27/storyforge.git
cd storyforge

# 2. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure — copy the template and fill in your keys
cp .env.example .env
#   then edit .env (see "Configuration" below)

# 4. Run the server
python main.py                       # starts Flask on :8080

# 5. Kick off one full episode, end-to-end
curl -X POST http://localhost:8080/run
```

Preview a brief + script **without** generating video or uploading:

```bash
python generate_script.py
```

## Configuration

All configuration is via environment variables in `.env` (see `.env.example`). Key groups:

- **`ANTHROPIC_API_KEY`** — scripts and briefs
- **`GOOGLE_SHEET_ID` + `GOOGLE_SHEETS_CREDENTIALS`** — the brief source sheet
- **`VIDEO_PROVIDER` / `IMAGE_PROVIDER` + provider keys** — media generation
- **`YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_OAUTH_TOKEN`** — upload (run `python generate_youtube_token.py` once to mint the token)
- **`CONTENT_PRESET`** — which preset drives genre, voice, style, and routing

> **No secrets are committed.** `.env` and all real credential files are git-ignored; only `.env.example` (with placeholder values) ships in the repo.

## Project layout

```
storyforge/
├── main.py               # Flask entry point
├── orchestrator.py       # Runs one episode end-to-end
├── config.py             # Presets, providers, model IDs
├── generate_script.py    # CLI: brief + script preview (no video/upload)
├── modules/              # brief/script/image/video generators, audio, upload, sheets
├── skills/               # Loadable craft "skills" injected into Claude's prompt
├── assets/               # Title/end card sources + render cache
└── scripts/              # Standalone utilities
```

## Tech

Python · Flask · Anthropic SDK · Google Sheets/YouTube APIs · `ffmpeg` · pluggable image/video model providers.

---

*Built as a personal experiment in fully autonomous, long-form AI content production.*
