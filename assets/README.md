# Assets — Title Cards, End Cards, Music

This folder holds preset-level video assets that get baked into every episode.

```
assets/
├── title_cards/         ← per-preset title card source files (PNG + MP3)
├── end_cards/           ← per-preset end card source files (PNG + MP3)
├── cache/               ← auto-generated MP4 cards (do not edit; safe to delete)
└── music/               ← legacy / unused (BGM now comes from ElevenLabs or Seedance native audio)
```

## How Title / End Cards Work

For each preset that has `title_card` or `end_card` configured in `config.py`,
the pipeline:

1. Reads `image` (PNG) and `audio` (MP3) source files from `assets/title_cards/` or `assets/end_cards/`
2. Builds an MP4 matching the current video format (resolution, aspect ratio, codec)
3. Caches the MP4 in `assets/cache/` keyed by SHA256 of inputs
4. Prepends the title MP4 and appends the end MP4 to the stitched shot list

**Cards are built ONCE and reused across every episode.** Changing the source
PNG or MP3 invalidates the cache automatically — next run rebuilds the card.

## Required File Format

### Title / End Card Image (PNG)

- **Format:** PNG (recommended) or JPG
- **Aspect ratio:** Match the video output (currently 9:16 vertical)
- **Recommended dimensions:** 720x1280 (matches 9:16 at 720p) — pipeline will scale/pad to current resolution
- **Background:** The pipeline pads with black if the image doesn't fill the frame
- **Tip:** Design with safe margins; mobile players crop edges

### Title / End Card Audio (MP3)

- **Format:** MP3 (recommended) or WAV
- **Length:** Match the `duration` in config (default 5 seconds)
- **Style:** A single sound sting works well; long ambient tracks get cut at `duration`
- **Optional:** If audio is missing, the pipeline builds a silent card

## Configuring a New Preset

In `config.py`, add to the preset's dict:

```python
"title_card": {
    "image": "assets/title_cards/zenith.png",
    "audio": "assets/title_cards/zenith_sting.mp3",
    "duration": 5.0,    # seconds
    "fade_in": 0.5,     # seconds; 0 to disable
    "fade_out": 0.3,    # seconds; 0 to disable
},
"end_card": {
    "image": "assets/end_cards/zenith.png",
    "audio": "assets/end_cards/zenith_sting.mp3",
    "duration": 5.0,
    "fade_in": 0.3,
    "fade_out": 0.8,
},
```

If any source file doesn't exist, that card is **silently skipped** — the
pipeline still produces a video, just without the card. This means you can
configure a preset's cards in `config.py` first, then drop in the assets later.

## Currently Configured Presets

| Preset | Title Card | End Card |
|--------|-----------|----------|
| preset-7 (Zenith Chronicles) | `zenith.png` + `zenith_sting.mp3` | `zenith.png` + `zenith_sting.mp3` |
| All others | (not configured) | (not configured) |

## Regenerating Cards

The cache is content-addressed — any change to the input files busts the cache:

- Swap the PNG → next run rebuilds the card
- Swap the MP3 → next run rebuilds the card
- Change duration / fade in `config.py` → next run rebuilds the card

To force a clean rebuild without changing inputs:

```bash
rm -rf assets/cache/*
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Card not appearing in video | Source file missing | Check path in `config.py` matches actual file |
| Card looks stretched | Source PNG aspect ratio wrong | Resize source to 9:16 (e.g., 720x1280) |
| Card audio cuts off / loops | Audio length ≠ `duration` | Trim audio to match, or adjust `duration` |
| Cache won't rebuild after changes | Same file mtime | Hashing uses bytes not mtime — should auto-rebuild; if not, `rm -rf assets/cache/*` |
| Stitched video has glitches at card seams | Codec mismatch | The pipeline auto re-encodes when cards are present; if you still see glitches, check ffmpeg version |

## Recommended Toolchain for Building Source Files

- **PNG:** Figma, Canva, GPT Image 2, Photoshop. Export at 720x1280 for best quality.
- **MP3:** ElevenLabs Sound Effects (text-to-sound), Audacity (free), GarageBand. Keep it under 5s.
