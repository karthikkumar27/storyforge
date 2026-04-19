# Cinematic AI Agent — Design Spec

**Date:** 2026-04-08  
**Status:** Approved

---

## Overview

An automated Python pipeline that runs daily at 10:00 PM UTC+8. It reads a story brief from Google Sheets, uses Claude to generate a cinematic sci-fi/horror/outer-space script, produces a 60–90 second video via Kling AI, adds AI voiceover (ElevenLabs) and atmospheric music, then uploads to YouTube and updates the GSheet row with the result.

The system also includes a **discovery mode** where Claude searches for and auto-selects the best available free AI video generation tools, with Kling AI as the current winner.

---

## Architecture

**Pattern:** Modular pipeline with Claude as orchestrator  
**Language:** Python  
**Hosting:** GCP Cloud Run (Docker container) + Cloud Scheduler  
**Trigger:** Cron `0 14 * * *` (10:00 PM UTC+8 daily)

### Modules

| Module | Responsibility |
|--------|---------------|
| `gsheet_reader` | Authenticates with Google Sheets API, finds first `pending` row, returns row data |
| `script_generator` | Calls Claude API with story brief + genre, returns narrative script + list of shot prompts (6–9 shots) |
| `video_producer` | Calls Kling AI API for each shot prompt, downloads MP4 clips, stitches with ffmpeg |
| `audio_mixer` | Selects ElevenLabs voice by genre, generates voiceover, overlays royalty-free music, mixes onto video with ffmpeg |
| `youtube_uploader` | Calls YouTube Data API v3, uploads final video, returns YouTube URL |
| `orchestrator` | Imports and calls each module in sequence, handles status updates and error propagation |

---

## Google Sheets Schema

| Column | Type | Description |
|--------|------|-------------|
| `title` | string | Optional video title hint |
| `story_brief` | string | 1–3 sentence idea. Claude generates full script from this. |
| `script_text` | string | Auto-filled by Claude after generation |
| `genre` | enum | `sci-fi` / `horror` / `space` / `blend` |
| `duration_sec` | int | Target duration in seconds (default: 75) |
| `status` | enum | `pending` → `generating` → `uploading` → `done` / `error` |
| `youtube_url` | string | Auto-filled after successful upload |
| `error_msg` | string | Auto-filled if `status=error` |

---

## Pipeline Flow

```
Cloud Scheduler (daily 10PM UTC+8)
        ↓
Cloud Function (orchestrator.py)
        ↓
1. gsheet_reader     → finds first pending row
        ↓
2. script_generator  → Claude generates script + 6–9 shot prompts
        ↓
3. video_producer    → Kling API × N shots → ffmpeg stitch → 60–90s MP4
        ↓
4. audio_mixer       → ElevenLabs voiceover + royalty-free music → ffmpeg mix
        ↓
5. youtube_uploader  → upload → get YouTube URL
        ↓
6. gsheet_reader     → update row: status=done, youtube_url=<url>
```

---

## Discovery Mode

A separate `discovery.py` module (run manually or on demand) uses Claude + web search to:
1. Search for current free AI video generation tools
2. Score each against a fixed rubric: free tier ✓, API access ✓, cinematic resolution ✓, story/narrative support ✓
3. Auto-select the highest scorer and write it to `config.py`

Current winner: **Kling AI** (primary), **HailuoAI** (fallback).

---

## Script Generation

Claude receives:
- `story_brief` from GSheet
- `genre` tag (sci-fi / horror / space / blend)
- System prompt defining cinematic style, tone, and shot structure

Claude outputs:
- `narrative_script`: full readable story (saved back to GSheet `script_text`)
- `shots`: list of 6–9 optimized Kling prompt strings (~10 sec per shot)

---

## Video Production

- **Tool:** Kling AI official API (`klingai.com`)
- **Auth:** JWT token generated from Access Key ID + Secret Key per request
- **Shot duration:** 5–10 seconds each
- **Total shots:** 6–9 (targeting 60–90 sec final video)
- **Stitching:** ffmpeg concatenates all clips into one MP4
- **Free tier usage:** ~18–27 credits per video (66 credits/day available)

---

## Audio

- **Voiceover:** ElevenLabs TTS (genre-adaptive voice selection)
  - sci-fi → Adam
  - horror → Arnold
  - space/blend → Antoni
- **Background music:** Royalty-free atmospheric MP3 files bundled in the repo under `assets/music/` (genre-tagged: sci-fi, horror, space)
- **Mixing:** ffmpeg blends voiceover + music at appropriate levels, overlays on video

---

## YouTube Upload

- **API:** YouTube Data API v3
- **Auth:** OAuth2 (user grants access once, refresh token stored securely)
- **Metadata:** Claude generates title, description, and tags from the narrative script
- **Phase 2:** TikTok + Instagram (requires platform app approval — out of scope for MVP)

---

## Error Handling

- Each module catches its own exceptions
- On failure: writes `status=error` and `error_msg` to GSheet row
- Pipeline halts for that row; other rows unaffected
- Rows in `error` status are skipped on subsequent runs unless manually reset to `pending`
- Cloud Function logs available in GCP Cloud Logging for debugging

---

## Credentials Required

| Credential | Source | Storage |
|-----------|--------|---------|
| Kling AI Access Key ID | klingai.com developer console | GCP Secret Manager |
| Kling AI Secret Key | klingai.com developer console | GCP Secret Manager |
| ElevenLabs API Key | elevenlabs.io | GCP Secret Manager |
| Google Sheets service account JSON | GCP IAM | GCP Secret Manager |
| YouTube OAuth2 refresh token | Google Cloud Console | GCP Secret Manager |
| Claude API key | console.anthropic.com | GCP Secret Manager |

---

## Dependencies

```
anthropic
gspread
google-auth
google-api-python-client
google-auth-oauthlib
requests
httpx
ffmpeg-python
apscheduler
python-dotenv
```

ffmpeg is included in the Docker image (`apt-get install ffmpeg`). This is why Cloud Run (not Cloud Functions) is used — it supports custom Docker containers with arbitrary binaries.

---

## Project Structure

```
idea-creator/
├── main.py                  # Cloud Run HTTP entrypoint (triggered by Cloud Scheduler)
├── orchestrator.py          # Pipeline orchestrator
├── modules/
│   ├── gsheet_reader.py
│   ├── script_generator.py
│   ├── video_producer.py
│   ├── audio_mixer.py
│   └── youtube_uploader.py
├── discovery.py             # Tool discovery mode (run manually)
├── config.py                # Active tool config (Kling as winner)
├── assets/
│   └── music/               # Bundled royalty-free MP3s (sci-fi.mp3, horror.mp3, space.mp3)
├── Dockerfile               # Installs Python deps + ffmpeg
├── requirements.txt
└── .env.example             # Template for local development
```

---

## Out of Scope (MVP)

- TikTok upload
- Instagram upload
- Multiple rows per day
- User-facing dashboard/UI
- Video preview before upload
