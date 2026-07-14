# Episode Archive

Local archive of every finished episode. Files are added automatically by `orchestrator.py` after the audio mix step but before YouTube upload — so even if upload fails, the video is preserved.

## Filename format

```
<YYYYMMDD-HHMM>_<title-slug>.mp4
```

Example: `20260502-2347_The-Chronicle-of-Zenith-Ep-1-The-Signal-Begins.mp4`

- Timestamp = generation completion (local time)
- Title slug = YouTube title with unsafe filename characters stripped, em-dashes flattened, spaces → hyphens, capped at 80 chars
- Same-minute collisions get `_1`, `_2`, ... suffixes appended

## What's NOT archived here

- Title/end card MP4s (those live in `../assets/cache/` and rebuild from source as needed)
- Per-shot intermediate clips (deleted with the temp directory after each run)
- Storyboards (the GPT Image 2 Edit URLs in the Atlas Cloud bucket are the source of truth)

## Pruning

This folder is `.gitignore`d (videos are too big to commit). Prune when it gets large — every episode is also on YouTube via the URL in the sheet's `youtube_url` column, so deleting locally is non-destructive.
