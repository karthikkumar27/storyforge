# Idea Creator — AI Video Pipeline

A fully automated pipeline that turns a story idea into a published YouTube video. Reads briefs from Google Sheets, generates scripts via Claude, creates reference images via GPT Image 2, generates video shots via Seedance, stitches with ffmpeg, and uploads to YouTube — all from a single `POST /run` call.

## Quick Reference

| Command | What it does |
|---------|-------------|
| `python main.py` | Start the Flask server (port 8080) |
| `curl -X POST http://localhost:8080/run` | Kick off one full episode end-to-end |
| `python generate_script.py` | Generate brief + script only (no video, no upload) — useful for previewing |
| `python scripts/generate_character_images.py` | Bulk-generate character reference images (preset-7 only) |
| `python scripts/export_characters.py` | Refresh `chronicle of zenith/chronicle-of-zenith-characters-locked.md` from the sheet |
| `python scripts/manual_episode.py` | Ad-hoc: read main sheet, generate video, save locally — no narration, no YouTube upload |

## Architecture Overview

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
                              Audio Mixer (ElevenLabs — skipped for atlas provider since Seedance has native audio)
                                       │
                                       ▼
                              YouTube Uploader
                                       │
                                       ▼
                              Sheet status → done + youtube_url
```

## Provider Stack (Atlas Cloud V2)

| Component | Provider | Model | Cost |
|-----------|----------|-------|------|
| LLM (briefs + scripts) | Anthropic | `claude-sonnet-4-6` | per-token |
| Reference images | Atlas Cloud (proxies OpenAI) | `openai/gpt-image-2/text-to-image` | $0.006/image |
| Video shots | Atlas Cloud (proxies BytePlus) | `bytedance/seedance-v1.5-pro/image-to-video-fast` (shot 1) + `text-to-video` (shots 2-N) | ~$0.18 per 10s clip |
| TTS / BGM (legacy, disabled for atlas) | ElevenLabs | `eleven_multilingual_v2` + Video-to-Music | per-character |
| Sheet I/O | Google Sheets API | gspread | free tier |
| Upload | YouTube Data API v3 | OAuth2 | free quota |

Set `VIDEO_PROVIDER=atlas` and `IMAGE_PROVIDER=atlas` in `.env`. To revert to v1 (BytePlus direct), use `seedance` and `seedream`.

## Project Layout

```
idea-creator/
├── main.py                   ← Flask entry point (load_dotenv MUST be first)
├── orchestrator.py           ← Pipeline runner — one episode end-to-end (takes a Deps bundle)
├── config.py                 ← All presets, providers, model IDs, atlas/byteplus URLs
├── generate_script.py        ← CLI: brief + script preview without video
├── generate_youtube_token.py ← One-time OAuth helper
│
├── modules/
│   ├── brief_generator.py    ← Story idea generation (Claude)
│   ├── script_generator.py   ← Shot list + narration generation (Claude)
│   ├── atlas_client.py       ← Atlas prediction protocol: submit → poll → outputs → download
│   ├── image_generator.py    ← Reference image generation (GPT Image 2 / Seedream)
│   ├── video_producer.py     ← Seedance/Kling/Atlas video producers (factory)
│   ├── audio_mixer.py        ← ElevenLabs TTS + BGM mixing (used when not atlas)
│   ├── youtube_uploader.py   ← OAuth2 + chunked upload
│   ├── episode_ledger.py     ← Episode Ledger — claim_next/start/record/finish/fail
│   ├── sheet_access.py       ← Sheet seam: cached reads, batched writes, gspread + in-memory adapters
│   ├── characters_reader.py  ← Preset-7 characters sheet (locked roster)
│   ├── preset.py             ← Active Preset as a value: capabilities, not identity checks
│   ├── storyboard.py         ← Per-shot storyboard frames (POV/wide detection + edit prompts)
│   ├── arc_context.py        ← Preset-7 episode_number → arc_number resolver
│   ├── skill_loader.py       ← Reads skills/*/SKILL.md and concatenates
│   └── title_card_renderer.py ← PNG+MP3 → MP4 with content-hash cache
│
├── skills/                   ← Loaded into Claude's system prompt at runtime
│   ├── storytelling-craft/        ← Common (all presets) — logline, want/need/wound
│   ├── episode-architecture/      ← Common — hook → development → turn → button
│   ├── character-consistency/     ← Common — locked paragraphs, outfit lock
│   ├── video-prompt-builder/      ← Common (script gen) — camera, lighting, POV
│   ├── screenplay-director/       ← Common (script gen) — screen direction, blocking
│   ├── kids-content-specialist/   ← Loaded only for preset-4/5/6
│   ├── chronicle-of-zenith-canon/ ← Loaded only for preset-7 — full series bible + roster
│   ├── story-architect/           ← Legacy (kept locally, not loaded by default)
│   └── youtube-shorts-optimizer/  ← Common (all presets, script generator) — 3-sec hooks, retention, tag strategy
│
├── chronicle of zenith/      ← REFERENCE DOCS for preset-7 (read these for context)
│   ├── chronicle-of-zenith-series-bible.md         ← Locked canon: themes, mythology, dark secret, arc map
│   ├── chronicle-of-zenith-character-roster.md     ← Original 21-character design roster
│   ├── chronicle-of-zenith-characters-locked.md    ← Runtime snapshot of the 15 currently in the sheet
│   ├── chronicle-of-zenith-story-guide.md          ← Storytelling craft + macro architecture
│   └── chronicle-of-zenith-production-workflow.md  ← Seedance + GPT Image 2 production pipeline
│
├── docs/                     ← Project documentation
│   └── alan-story-sheets-schema.md  ← Schema for preset-7's two dedicated sheets
│
├── assets/                   ← Title/end card source files + cache
│   ├── title_cards/          ← PNG + MP3 source files (per preset)
│   ├── end_cards/            ← PNG + MP3 source files (per preset)
│   ├── cache/                ← Auto-generated MP4 cards (content-hash keyed)
│   └── README.md             ← How to drop in title/end card assets
│
└── scripts/                  ← Standalone utilities (not part of pipeline)
    ├── generate_character_images.py  ← Bulk character ref image generation (preset-7)
    └── export_characters.py          ← Sheet → markdown snapshot
```

## Content Presets

| Preset | Name | Genres | Mode | Voice | Notes |
|--------|------|--------|------|-------|-------|
| `preset-1` | Dark Cinematic | sci-fi, space | series (3 parts) | Adam | Photorealistic |
| `preset-2` | Shoujo Anime Comedy | school-romance, magical-girl, slice-of-life, chibi-chaos | standalone | Jessica | Anime |
| `preset-3` | Fantasy/Mythology | fantasy, mythology, supernatural, steampunk | series (3 parts) | Adam | Photorealistic fantasy |
| `preset-4` | Kids — Toddler Rhymes | nursery-rhyme, counting-song, animal-song, lullaby | series (999) | Laura | Singing cat |
| `preset-5` | Kids — Mini Mart Cat | mini-mart-adventure, customer-chaos, shelf-stacking, delivery-day | series (999) | Callum | Cat shopkeeper |
| `preset-6` | Kids — Croc Academy | science-lesson, math-fun, nature-explore, history-adventure | series (999) | Liam | 3D animated |
| `preset-7` | **Zenith Chronicles** | origin-story, transformation, galaxy-quest, earth-encounter | series (999, but really 200) | Adam | **Special — see below** |

Set `CONTENT_PRESET=preset-N` in `.env`. The active preset drives genre, voice, video style, story mode, sheet routing, skill loading, and YouTube category.

## Preset-7 — The Chronicle of Zenith

**This is the flagship preset and has dramatically more architecture than the others.** Read these files in `chronicle of zenith/` before working on it:

| Document | Purpose |
|----------|---------|
| `chronicle-of-zenith-series-bible.md` | **Locked canon** — themes, mythology, the dark secret, the 10-arc map, characters, ending |
| `chronicle-of-zenith-character-roster.md` | Full 21-character design with cut/keep recommendations |
| `chronicle-of-zenith-characters-locked.md` | **Runtime snapshot** of what's actually in the sheet right now |
| `chronicle-of-zenith-story-guide.md` | Storytelling craft principles + macro architecture for the series |
| `chronicle-of-zenith-production-workflow.md` | Seedance + GPT Image 2 production playbook |

### What makes preset-7 special

- **200-episode continuous series** in 10 arcs of 20 episodes each
- **Dedicated Google Sheet** for episodes (`ALAN_STORY_GOOGLE_SHEET_ID`) — separate from main `GOOGLE_SHEET_ID`
- **Dedicated characters sheet** (`ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID`) with locked appearance paragraphs and reference image URLs for 15 characters
- **Arc context auto-injected** into every brief — Claude knows which arc it's writing for
- **Form-aware ref image selection** — Claude declares `character_form: normal | transformed | both` and the pipeline picks the matching locked reference image (Alan vs Zenith)
- **Episode-numbered YouTube titles** — `"The Chronicle of Zenith — Ep N: {Episode Title}"`
- **Locked character paragraphs** — every character description is pasted verbatim into Claude's context, fighting drift across 200 episodes
- **Title/end cards** — configured (zenith.png + zenith_sting.mp3); pipeline auto-builds MP4 from PNG+MP3 once and caches forever

### Skill stack for preset-7

When preset-7 is active, the script generator loads:

1. `storytelling-craft` — universal craft principles
2. `episode-architecture` — universal short-form format rules
3. `character-consistency` — locked paragraphs / outfit lock / hero ref / two-gen rule
4. `video-prompt-builder` — camera, shot variety, POV, lighting
5. `screenplay-director` — screen direction, action choreography
6. `chronicle-of-zenith-canon` — full series bible + 15-character roster

The brief generator loads only `storytelling-craft`, `episode-architecture`, and `chronicle-of-zenith-canon` (visual skills are post-brief).

### How a preset-7 episode flows through the pipeline

```
1. Orchestrator calls get_episode_reader() → routes to ALAN_STORY_GOOGLE_SHEET_ID
2. No pending row → compute next episode_number from sheet (max done + 1)
3. arc_context.resolve_arc(episode_number) → arc_number, arc_title, arc_question
4. CharactersReader.format_characters_context(arc_number) → injects active cast paragraphs
5. Brief generator builds system prompt = arc_context + characters_context + canon skill + craft skills + brief template
6. Claude writes brief, including character_form: "normal" | "transformed" | "both"
7. Sheet auto-adds arc_number, episode_number, character_form columns; appends new pending row
8. Script generator builds shots (using same canon + visual skills)
9. CharactersReader.get_main_ref_image_for_form(form) → returns Alan's normal or Zenith's transformed URL from sheet
10. (Skipped if URL exists in sheet) Image Generator generates fresh image
11. Video Producer:
    - Shot 1: image-to-video using locked ref image as first frame
    - Shots 2-6: text-to-video (no first frame, scene variety)
    - Title card prepended (cached MP4) if assets exist
    - End card appended (cached MP4) if assets exist
12. Stitched with ffmpeg
13. Audio mixer SKIPPED (Seedance has native audio for atlas provider)
14. YouTube uploader: title formatted as "The Chronicle of Zenith — Ep N: {title}"
15. Sheet status → uploading → done + youtube_url
```

## Working with Each Preset

### When user mentions any preset

- Default genres, voice, style, story mode, etc. are in `config.py` under `PRESETS["preset-N"]`
- The active preset is read from `CONTENT_PRESET` env var
- Switching presets requires restarting Flask (Python imports don't auto-reload `config.py`)

### Adding a new character (preset-7 only)

1. Open the characters Google Sheet (`ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID`)
2. Add a row with: `character_name`, `appearance_normal`, `arcs_active` (e.g. `"4,5,6"`)
3. Optionally fill `appearance_transformed`, `relation_to_main`, `backstory`, `first_episode`, `status`
4. Run `python scripts/generate_character_images.py` → bulk-generate ref images for new rows
5. Run `python scripts/export_characters.py` → refresh markdown snapshot

### Generating reference images defensively

GPT Image 2 has a **safety filter** that refuses real-person-style descriptions. The script auto-handles this with three retry strategies:

1. **Retry 0**: Original text + "Stylized anime illustration of a fictional original character" framing
2. **Retry 1**: Soften gendered nouns (`woman` → `female character`, `man` → `male character`)
3. **Retry 2**: Aggressive strip — remove skin colors, ethnic markers, age fragments, and emotional/relationship sentences

If a character still fails after all 3 retries, options are:

- Edit the appearance paragraph in the sheet (e.g. soften "Late 60s woman" to "older female figure")
- Manually generate via Atlas playground and paste the URL into the sheet's `ref_image_normal` cell
- Skip the problem character and continue: `--skip "Edith Hale"`

## Environment Variables

```bash
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Google Sheets (main sheet for non-preset-7)
GOOGLE_SHEET_ID=...
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account",...}

# Preset-7 dedicated sheets
ALAN_STORY_GOOGLE_SHEET_ID=...                  # Episode timeline
ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID=...       # Character roster

# Provider routing (default both atlas)
VIDEO_PROVIDER=atlas         # atlas | seedance | kling
IMAGE_PROVIDER=atlas         # atlas | seedream

# Atlas Cloud (unified — both image and video)
ATLASCLOUD_API_KEY=apikey-...
ATLAS_POLL_INTERVAL_SEC=15   # optional, default 15
ATLAS_MAX_POLL_ATTEMPTS=60   # optional, default 60

# BytePlus (legacy v1)
ARK_API_KEY=...

# Kling (legacy)
KLING_ACCESS_KEY_ID=...
KLING_SECRET_KEY=...

# YouTube
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_OAUTH_TOKEN={"token":"...","refresh_token":"..."}

# ElevenLabs (used when VIDEO_PROVIDER != atlas)
ELEVENLABS_API_KEY=sk_...

# Active preset
CONTENT_PRESET=preset-7

# Local Flask port
PORT=8080
```

## Common Pitfalls

| Symptom | Cause | Fix |
|---------|-------|-----|
| `KeyError: 'CONTENT_PRESET'` always defaults to preset-1 | `load_dotenv()` runs after `from orchestrator import ...` | Move `load_dotenv()` BEFORE all imports in `main.py` |
| Pipeline always picks preset-1 even after switching `.env` | Python module cache — config resolved at import time | Restart Flask after changing `.env` |
| `429 Too Many Requests` from Atlas | Polling too aggressively | Increase `ATLAS_POLL_INTERVAL_SEC` to 20-30 |
| `arcs_active` shows as `12345` integer instead of comma string | Google Sheets auto-numericising | Cell was prefixed with `'` to force text format; reader uses `numericise_ignore=['all']` |
| Character image generation 500 / safety filter | Real-person-style description | The script's 3-tier retry handles most; for stubborn ones use `--skip` and manually generate |
| Preset-7 ignores arc context | `episode_number` not computed/passed | Orchestrator computes it from `get_next_episode_number(GENRES)` for preset-7 only |
| Browser can't play final video | Mixed source codecs in `-c copy` concat | Stitcher auto re-encodes when title/end cards are present |
| YouTube upload `invalid_grant: Token has been expired or revoked` | OAuth refresh token expired | Re-run `python generate_youtube_token.py` |

## Cost Reference (rough, per episode)

### Preset-7 (Zenith) — typical episode

| Step | Cost |
|------|------|
| Brief + script (Claude) | ~$0.03 |
| Reference image (skipped — locked URL exists) | $0.00 |
| 6 × 10s video shots (Atlas Seedance 1.5 Pro Fast) | ~$1.08 |
| Audio (Seedance native, no ElevenLabs) | $0.00 |
| YouTube upload | $0.00 |
| **Total per episode** | **~$1.10** |

200 episodes × $1.10 = **~$220** for the entire Chronicle of Zenith series.

### Other presets (using ElevenLabs voiceover + BGM)

Add ~$0.30/episode for ElevenLabs TTS + Video-to-Music BGM.

## Working Notes for Future Sessions

- **Don't touch the characters sheet manually unless adding new characters.** It's the source of truth at runtime; the markdown snapshot is regenerated from it.
- **The series bible is locked canon.** Don't retcon facts unless the user explicitly asks.
- **Loaded skills cap around 50KB total for preset-7** — that's ~12K tokens of context. The investment is worth it for continuity.
- **YouTube title format for preset-7 is `"The Chronicle of Zenith — Ep N: {title}"`** — automatic, in `orchestrator.py`.
- **Atlas polling intervals**: 2s for images, 15s for video (configurable via env). Don't go below 5s on video or you'll hit 429.
- **Title/end cards are optional** — the pipeline gracefully skips when source assets are missing. They're built once via PNG+MP3 → MP4 with content-hash cache.
- **The form-aware ref image fallback chain**: characters sheet (form-matched) → series Part 1 reuse → preset default_ref_image → fresh GPT Image 2 generation. Almost always lands on step 1 for preset-7 once the sheet is populated.

## Phase History

The architecture was built in 6 incremental phases (all on the `atlas-cloud-v2` branch):

1. **Phase 1** — Common skills (storytelling-craft, episode-architecture, character-consistency) + chronicle-of-zenith-canon
2. **Phase 2** — Arc/episode tracking (200-ep map, sheet columns auto-added, episode-numbered titles)
3. **Phase 3** — Title/end card pre-rendering (PNG+MP3 → MP4 with cache)
4. **Phase 4** — Dedicated Alan Story sheets (preset-aware routing, characters sheet, locked paragraph injection)
5. **Phase 5** — Form-aware reference image selection (Alan vs Zenith based on episode form)
6. **Phase 6** — Standalone bulk character image generation script (`scripts/generate_character_images.py`)
