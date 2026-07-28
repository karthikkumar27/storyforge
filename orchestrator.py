import re
import shutil
from datetime import datetime
from pathlib import Path

from config import STORY_MODE, VIDEO_PROVIDER, ACTIVE_PRESET, GENRES, VIDEO_STYLE, DEFAULT_TAGS, _preset
from modules.episode_ledger import get_episode_ledger
from modules.sheet_access import SheetSession
from modules.brief_generator import BriefGenerator
from modules.script_generator import ScriptGenerator
from modules.image_generator import create_image_generator
from modules.video_producer import (
    create_video_producer,
    AtlasSeedance2I2VLoopProducer,
    AtlasSeedance2T2VProducer,
    AtlasSeedance1_5T2VFastProducer,
)
from modules.audio_mixer import AudioMixer
from modules.youtube_uploader import YouTubeUploader


PROJECT_ROOT = Path(__file__).parent
VIDEOS_DIR = PROJECT_ROOT / "videos"



def _slugify_title(title: str, max_len: int = 80) -> str:
    """Make a YouTube title safe to use as a filename. Keeps a readable form
    (spaces preserved as hyphens, em-dashes flattened) and caps total length."""
    if not title:
        return "untitled"
    slug = title.replace("—", "-").replace("–", "-").replace("…", "")
    # Drop characters that are unsafe / annoying in filenames across macOS, Windows, and Linux
    slug = re.sub(r'[\\/*?:"<>|]', "", slug)
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    return slug[:max_len].rstrip("-_")


def _archive_video(source_path: str, title: str) -> str | None:
    """Copy a finished episode MP4 into videos/ with a human-readable filename.
    Returns the destination path on success, None on any error (archiving
    should never block the pipeline)."""
    try:
        VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        slug = _slugify_title(title)
        dest = VIDEOS_DIR / f"{timestamp}_{slug}.mp4"
        # If the same minute saw two videos (rare, but possible during retries),
        # bump the suffix instead of overwriting
        n = 1
        while dest.exists():
            dest = VIDEOS_DIR / f"{timestamp}_{slug}_{n}.mp4"
            n += 1
        shutil.copy2(source_path, dest)
        return str(dest)
    except Exception as exc:
        print(f"[Pipeline] Archive failed (non-fatal): {exc}", flush=True)
        return None


def _run_single_shot_native() -> dict:
    """Simplified pipeline for presets where Seedance 2.0 generates the whole
    video (including audio) in one call. Flow: pending row → submit prompt →
    download MP4 → archive → upload. No script gen, no per-shot storyboards,
    no stitching, no audio mixing.
    """
    session = SheetSession()
    ledger = get_episode_ledger(session)
    claim = ledger.claim_next()

    if claim.needs_brief:
        brief_data = BriefGenerator(session).generate(**claim.brief_context.as_kwargs())
        claim = ledger.start(brief_data)

    if claim.episode is None:
        return {"status": "no_pending_rows"}

    episode = claim.episode
    row_index = episode.row_index
    try:
        ledger.record(row_index, status="generating")

        seedance2_cfg = _preset.get("seedance2") or {}
        mode = seedance2_cfg.get("mode", "t2v")
        prompt = episode.story_brief
        print(f"[Drone] Mode={mode}  brief ({len(prompt)} chars): {prompt[:200]}...", flush=True)

        if mode == "i2v-loop":
            # Ambient loop mode — generate a still anchor, pass it as BOTH the
            # first and last frame to Seedance i2v. Kept for future ambient
            # presets; not currently used by preset-8.
            ref_image_url = (episode.ref_image_url or "").strip()
            if ref_image_url:
                print(f"[Drone] Reusing ref image from sheet: {ref_image_url[:80]}...", flush=True)
            else:
                from modules.image_generator import AtlasImageGenerator
                image_model = _preset.get("image_model")
                print(f"[Drone] Generating loop-anchor still ({image_model or 'default'})...", flush=True)
                ref_image_url = AtlasImageGenerator().generate(prompt, model=image_model)
                ledger.record(row_index, ref_image_url=ref_image_url)
                print(f"[Drone] Still generated: {ref_image_url[:80]}...", flush=True)
            video_path = AtlasSeedance2I2VLoopProducer().produce(
                image_url=ref_image_url,
                motion_prompt=prompt,
                params=seedance2_cfg,
            )
        else:
            # Cinematic action mode (preset-8 default). No image anchoring —
            # Seedance has full creative freedom. Each clip ends mid-action.
            # Branch on model_variant: "1.5-fast" uses the cheap Seedance 1.5
            # Pro Fast producer (~12x cheaper, no native audio, 10s max).
            # Default "2.0" uses Seedance 2.0 with native audio.
            variant = seedance2_cfg.get("model_variant", "2.0")
            if variant == "1.5-fast":
                print(f"[Drone] Using Seedance 1.5 Pro Fast (cheap, silent)", flush=True)
                video_path = AtlasSeedance1_5T2VFastProducer().produce(prompt, seedance2_cfg)
            else:
                print(f"[Drone] Using Seedance 2.0 (native audio, expensive)", flush=True)
                video_path = AtlasSeedance2T2VProducer().produce(prompt, seedance2_cfg)

        # Title for YouTube — prefer the title field if the brief had a
        # title_hint, otherwise fall back to a generic timestamped title.
        title = (episode.title or "").strip() or "Endless Drone — Cinematic Aerial"

        # Reuse the orchestrator's archive helper so the MP4 lands in
        # videos/<date>_<slug>.mp4 with the same naming convention.
        archive_path = _archive_video(video_path, title)
        if archive_path:
            print(f"[Drone] Archived to {archive_path}", flush=True)

        ledger.record(row_index, status="uploading")
        # YouTubeUploader expects a script_result-like dict with title +
        # description + tags. Build a minimal one from the brief.
        script_result = {
            "title": title,
            "description": prompt,        # the drone prompt makes a fine description
            # Content tags first (genres + cinematic descriptors), then base
            # AI/model tags from DEFAULT_TAGS. Dedupe case-insensitively in case
            # any default term overlaps with the genre list.
            "tags": (
                lambda content: content + [t for t in DEFAULT_TAGS if t.lower() not in {c.lower() for c in content}]
            )(list(GENRES) + ["drone", "cinematic", "shorts", "ambient"]),
            "narrative": "",              # unused for this preset
        }
        youtube_url = YouTubeUploader().upload(archive_path or video_path, script_result)
        ledger.finish(row_index, youtube_url)
        return {"status": "done", "youtube_url": youtube_url}

    except Exception as exc:
        try:
            ledger.fail(row_index, str(exc))
        except Exception:
            pass
        raise


def run_pipeline() -> dict:
    # Single-shot native presets (preset-8 Drone Shorts) bypass the
    # script/image/storyboard/stitcher/audio-mixer pipeline entirely — they
    # just generate a prompt, send it to Seedance 2.0 (which produces video +
    # audio in one call), and upload. Branched at the top so the rest of this
    # function stays focused on the shot-assembly flow.
    if _preset.get("pipeline_mode") == "single_shot_native":
        return _run_single_shot_native()

    # One SheetSession per Run — reads are cached for its lifetime and discarded
    # afterwards, so material edited between Runs is picked up.
    # See docs/adr/0001-run-scoped-ledger-cache.md.
    session = SheetSession()
    ledger = get_episode_ledger(session)

    # Routes to ALAN_STORY sheet for preset-7, main GOOGLE_SHEET for everything
    # else. Resolves the anti-repetition history, the Series so far, and the next
    # Episode Number in one read.
    claim = ledger.claim_next()

    if claim.needs_brief:
        brief_data = BriefGenerator(session).generate(**claim.brief_context.as_kwargs())
        claim = ledger.start(brief_data)

    if claim.episode is None:
        return {"status": "no_pending_rows"}

    episode = claim.episode
    row_index = episode.row_index

    try:
        ledger.record(row_index, status="generating")

        script_result = ScriptGenerator(session).generate(
            episode.story_brief,
            episode.genre,
            arc_number=episode.arc_number,
            episode_number=episode.episode_number,
        )
        # Buffered — rides along with the next status transition.
        ledger.record(row_index, script=script_result["narrative"])

        ref_image_url = None

        # Preset-7 — form-aware lookup from the characters sheet (Alan vs Zenith).
        # This takes priority over legacy series-id reuse and preset defaults so
        # each episode uses the right form's locked image.
        if ACTIVE_PRESET == "preset-7":
            from modules.characters_reader import CharactersReader
            chars = CharactersReader(session)
            form = str(episode.character_form).strip().lower() or "normal"
            ref_image_url = chars.get_main_ref_image_for_form(form)
            if ref_image_url:
                print(f"[Pipeline] Preset-7 character_form={form} → locked ref image from characters sheet", flush=True)
            else:
                print(f"[Pipeline] Preset-7 character_form={form} but no locked ref image yet — will generate fresh", flush=True)

        # Reuse reference image from Part 1 if this is a series continuation (other presets)
        if not ref_image_url and STORY_MODE == "series":
            series_id = ledger.latest_incomplete_series()
            if series_id:
                parts = ledger.series_parts(series_id)
                for part in parts:
                    url = part.get("ref_image_url", "")
                    if url:
                        ref_image_url = url
                        print(f"[Pipeline] Reusing reference image from Part {part.get('part_number', '?')}", flush=True)
                        break

        # Use preset's default reference image if configured
        if not ref_image_url and _preset.get("default_ref_image"):
            ref_image_url = _preset["default_ref_image"]
            print(f"[Pipeline] Using preset default reference image", flush=True)

        # Generate new reference image only if we don't have one
        if not ref_image_url:
            char_prompt = script_result.get("character_image_prompt")
            if char_prompt:
                ref_image_url = create_image_generator().generate(char_prompt)
                print("[Pipeline] New reference image generated", flush=True)

        # Save reference image URL to sheet for future parts (buffered)
        if ref_image_url:
            ledger.record(row_index, ref_image_url=ref_image_url)

        # Premium: per-shot storyboard generation. Opt-in per preset via
        # `per_shot_storyboards: True` in config. For each shot, GPT Image 2
        # Edit takes the reference image as the base and the shot's scene
        # description as the prompt, producing a shot-appropriate first frame
        # that preserves the character's identity. Solves wallpaper-effect
        # and character drift across shots.
        storyboard_urls: list[str | None] | None = None
        if _preset.get("per_shot_storyboards") and ref_image_url:
            storyboard_urls = []
            shots = script_result["shots"]
            print(f"[Pipeline] Generating {len(shots)} per-shot storyboards (Premium)...", flush=True)
            from modules.image_generator import AtlasImageGenerator
            edit_gen = AtlasImageGenerator()
            for i, shot_prompt in enumerate(shots):
                # Build the storyboard edit prompt. Two modes:
                #
                # 1. Character-present (default): preserve the main character's
                #    face/outfit from the reference image, allow supporting
                #    characters from the shot text into the frame.
                # 2. Character-absent (POV / extreme-wide / exterior shots): use
                #    the reference image only as a STYLE anchor (cel-shaded look,
                #    color palette, world). The main character must not be in
                #    frame because the shot text says so explicitly.
                #
                # We detect mode 2 via markers the script generator already writes
                # for POV / wide shots (these come from video-prompt-builder skill).
                low = shot_prompt.lower()
                character_absent = any(m in low for m in (
                    "pov shot", "pov push", "pov dolly",
                    "extreme wide", "ews ", "ews,", "ews.",
                    "from outside the ship", "outside the ship",
                    "no character", "character is not visible", "character not visible",
                    "camera pushes through", "camera dollies forward into",
                    "the world widening", "the ship growing smaller",
                ))

                if character_absent:
                    edit_prompt = (
                        f"Use the reference image as a STYLE anchor only — preserve the {VIDEO_STYLE} "
                        f"illustration style, color palette, and the world established in the reference. "
                        f"The main character should NOT be in frame for this shot (it is a POV, "
                        f"wide-exterior, or environmental shot). Render the scene exactly as the shot "
                        f"prompt describes, as a 9:16 vertical still frame at the START of the action, "
                        f"no motion blur. Scene: {shot_prompt}"
                    )
                else:
                    edit_prompt = (
                        f"Use the reference image as the base — preserve the main character's face, "
                        f"hair, outfit, and {VIDEO_STYLE} style exactly. Render this scene as a 9:16 "
                        f"vertical still frame at the START of the action, no motion blur. If the shot "
                        f"prompt explicitly names other characters or entities (a holographic AI "
                        f"manifesting as light, another person, a creature), include them rendered "
                        f"exactly as the shot prompt describes. Scene: {shot_prompt}"
                    )
                try:
                    sb_url = edit_gen.edit_image(ref_image_url, edit_prompt)
                    storyboard_urls.append(sb_url)
                    print(f"[Pipeline]   shot {i+1} storyboard ✓", flush=True)
                except Exception as exc:
                    print(f"[Pipeline]   shot {i+1} storyboard FAILED ({exc}), falling back to locked ref", flush=True)
                    storyboard_urls.append(None)  # falls back to ref_image_url in producer

        video_path = create_video_producer().produce(
            script_result["shots"],
            reference_image_url=ref_image_url,
            storyboard_urls=storyboard_urls,
        )

        # Audio mix routing:
        # 1. Preset configures `audio_mix.mode = "narration_over_native"` →
        #    layer ElevenLabs narration over Seedance's native audio (preset-7).
        # 2. VIDEO_PROVIDER=atlas without that config → use Seedance native only.
        # 3. Other providers → full ElevenLabs voiceover + BGM (legacy v1 path).
        audio_mix_cfg = _preset.get("audio_mix") or {}
        if audio_mix_cfg.get("mode") == "narration_over_native":
            # Auto-derive title/end card durations so narration stays inside
            # the story segment (doesn't overlap brand container audio stings)
            title_duration = (_preset.get("title_card") or {}).get("duration", 0.0)
            end_duration = (_preset.get("end_card") or {}).get("duration", 0.0)
            final_path = AudioMixer().mix_with_native_audio(
                video_path,
                script_result["narrative"],
                episode.genre,
                narration_volume=audio_mix_cfg.get("narration_volume", 1.0),
                ambient_volume=audio_mix_cfg.get("ambient_volume", 0.32),
                narration_start_offset=audio_mix_cfg.get("narration_start_offset", title_duration),
                narration_end_buffer=audio_mix_cfg.get("narration_end_buffer", end_duration),
            )
        elif VIDEO_PROVIDER == "atlas":
            final_path = video_path
            print("[Pipeline] Using Seedance native audio, skipping ElevenLabs", flush=True)
        else:
            final_path = AudioMixer().mix(video_path, script_result["narrative"], episode.genre)

        # Format YouTube title.
        # Preset-7 (Zenith): "The Chronicle of Zenith — Ep {N}: {Episode Title}"
        # Other series presets: "Series Title: Episode Title - Part N"
        if ACTIVE_PRESET == "preset-7" and episode.episode_number:
            ep_n = episode.episode_number
            episode_title = script_result["title"]
            script_result["title"] = f"The Chronicle of Zenith — Ep {ep_n}: {episode_title}"
            print(f"[Pipeline] YouTube title: {script_result['title']}", flush=True)
        elif episode.story_mode == "series" and episode.part_number:
            part_num = episode.part_number
            episode_title = script_result["title"]
            # Get series title from Part 1
            series_id = episode.series_id
            series_title = episode_title  # fallback
            if series_id:
                parts = ledger.series_parts(series_id)
                if parts:
                    series_title = parts[0].get("title", episode_title)
            if str(part_num) == "1":
                script_result["title"] = f"{episode_title} - Part 1"
            else:
                script_result["title"] = f"{series_title}: {episode_title} - Part {part_num}"
            print(f"[Pipeline] YouTube title: {script_result['title']}", flush=True)

        # Archive a permanent local copy under videos/ before the upload step.
        # File is saved even if YouTube upload fails — useful for retries and
        # for the rare case where you want to re-upload manually.
        archive_path = _archive_video(final_path, script_result.get("title", ""))
        if archive_path:
            print(f"[Pipeline] Archived to {archive_path}", flush=True)

        # Flushes the buffered script + ref image along with the status change.
        ledger.record(row_index, status="uploading")
        youtube_url = YouTubeUploader().upload(final_path, script_result)

        ledger.finish(row_index, youtube_url)
        return {"status": "done", "youtube_url": youtube_url}

    except Exception as exc:
        try:
            ledger.fail(row_index, str(exc))
        except Exception:
            pass
        raise
