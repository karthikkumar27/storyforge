import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from config import STORY_MODE, VIDEO_PROVIDER, GENRES, VIDEO_STYLE, DEFAULT_TAGS
from modules.preset import active_preset
from modules.characters_reader import CharactersReader
from modules.episode_ledger import get_episode_ledger
from modules.sheet_access import SheetSession
from modules.brief_generator import BriefGenerator
from modules.script_generator import ScriptGenerator
from modules.image_generator import AtlasImageGenerator, create_image_generator
from modules.video_producer import (
    create_video_producer,
    AtlasSeedance2I2VLoopProducer,
    AtlasSeedance2T2VProducer,
    AtlasSeedance1_5T2VFastProducer,
)
from modules.audio_mixer import AudioMixer
from modules.storyboard import build_storyboards, ChainedStoryboards
from modules.youtube_uploader import YouTubeUploader


PROJECT_ROOT = Path(__file__).parent
VIDEOS_DIR = PROJECT_ROOT / "videos"

_preset = active_preset()


@dataclass
class Deps:
    """Everything run_pipeline talks to.

    Fields are *factories*, not instances, so nothing is constructed until the
    pipeline reaches it. That matters: YouTubeUploader refreshes an OAuth token
    in its constructor, and an episode should not pay for that before its video
    exists.

    Production calls `run_pipeline()` and gets these defaults. Tests construct a
    Deps with the two or three collaborators they care about and leave the rest,
    which is why no test needs to patch a name inside this module.
    """

    session: SheetSession = field(default_factory=SheetSession)
    ledger: Callable[[SheetSession], Any] = get_episode_ledger
    brief_generator: Callable[[SheetSession], Any] = BriefGenerator
    script_generator: Callable[[SheetSession], Any] = ScriptGenerator
    characters: Callable[[SheetSession], Any] = CharactersReader
    image_generator: Callable[[], Any] = create_image_generator
    atlas_image_generator: Callable[[], Any] = AtlasImageGenerator
    storyboards: Callable[..., list] = build_storyboards
    chained_storyboards: Callable[..., Any] = ChainedStoryboards
    video_producer: Callable[[], Any] = create_video_producer
    audio_mixer: Callable[[], Any] = AudioMixer
    uploader: Callable[[], Any] = YouTubeUploader
    # Single-shot native presets pick one of these by config.
    loop_producer: Callable[[], Any] = AtlasSeedance2I2VLoopProducer
    seedance2_producer: Callable[[], Any] = AtlasSeedance2T2VProducer
    seedance15_producer: Callable[[], Any] = AtlasSeedance1_5T2VFastProducer



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


def _run_single_shot_native(deps: Deps) -> dict:
    """Simplified pipeline for presets where Seedance 2.0 generates the whole
    video (including audio) in one call. Flow: pending row → submit prompt →
    download MP4 → archive → upload. No script gen, no per-shot storyboards,
    no stitching, no audio mixing.
    """
    session = deps.session
    ledger = deps.ledger(session)
    claim = ledger.claim_next()

    if claim.needs_brief:
        brief_data = deps.brief_generator(session).generate(**claim.brief_context.as_kwargs())
        claim = ledger.start(brief_data)

    if claim.episode is None:
        return {"status": "no_pending_rows"}

    episode = claim.episode
    row_index = episode.row_index
    try:
        ledger.record(row_index, status="generating")

        seedance2_cfg = _preset.seedance2 or {}
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
                image_model = _preset.image_model
                print(f"[Drone] Generating loop-anchor still ({image_model or 'default'})...", flush=True)
                ref_image_url = deps.atlas_image_generator().generate(prompt, model=image_model)
                ledger.record(row_index, ref_image_url=ref_image_url)
                print(f"[Drone] Still generated: {ref_image_url[:80]}...", flush=True)
            video_path = deps.loop_producer().produce(
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
                video_path = deps.seedance15_producer().produce(prompt, seedance2_cfg)
            else:
                print(f"[Drone] Using Seedance 2.0 (native audio, expensive)", flush=True)
                video_path = deps.seedance2_producer().produce(prompt, seedance2_cfg)

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
        youtube_url = deps.uploader().upload(archive_path or video_path, script_result)
        ledger.finish(row_index, youtube_url)
        return {"status": "done", "youtube_url": youtube_url}

    except Exception as exc:
        try:
            ledger.fail(row_index, str(exc))
        except Exception:
            pass
        raise


def run_pipeline(deps: Deps | None = None) -> dict:
    # Single-shot native presets (preset-8 Drone Shorts) bypass the
    # script/image/storyboard/stitcher/audio-mixer pipeline entirely — they
    # just generate a prompt, send it to Seedance 2.0 (which produces video +
    # audio in one call), and upload. Branched at the top so the rest of this
    # function stays focused on the shot-assembly flow.
    deps = deps or Deps()

    if _preset.is_single_shot_native:
        return _run_single_shot_native(deps)

    # One SheetSession per Run — reads are cached for its lifetime and discarded
    # afterwards, so material edited between Runs is picked up.
    # See docs/adr/0001-run-scoped-ledger-cache.md.
    session = deps.session
    ledger = deps.ledger(session)

    # Routes to ALAN_STORY sheet for preset-7, main GOOGLE_SHEET for everything
    # else. Resolves the anti-repetition history, the Series so far, and the next
    # Episode Number in one read.
    claim = ledger.claim_next()

    if claim.needs_brief:
        brief_data = deps.brief_generator(session).generate(**claim.brief_context.as_kwargs())
        claim = ledger.start(brief_data)

    if claim.episode is None:
        return {"status": "no_pending_rows"}

    episode = claim.episode
    row_index = episode.row_index

    try:
        ledger.record(row_index, status="generating")

        script_result = deps.script_generator(session).generate(
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
        if _preset.serialized_canon:
            chars = deps.characters(session)
            form = str(episode.character_form).strip().lower() or "normal"
            ref_image_url = chars.get_main_ref_image_for_form(form)
            if ref_image_url:
                print(f"[Pipeline] Preset-7 character_form={form} → locked ref image from characters sheet", flush=True)
            else:
                print(f"[Pipeline] Preset-7 character_form={form} but no locked ref image yet — will generate fresh", flush=True)

        # Reuse reference image from Part 1 if this is a series continuation
        # (other presets). The words that describe that image live on the
        # SAME earlier, completed row — not the current, still-pending one —
        # so they travel together into `series_appearance` and feed the
        # priority chain below as this run's saved value.
        series_appearance: str | None = None
        if not ref_image_url and STORY_MODE == "series":
            series_id = ledger.latest_incomplete_series()
            if series_id:
                parts = ledger.series_parts(series_id)
                for part in parts:
                    url = part.get("ref_image_url", "")
                    if url:
                        ref_image_url = url
                        series_appearance = str(part.get("character_appearance", "")).strip() or None
                        print(f"[Pipeline] Reusing reference image from Part {part.get('part_number', '?')}", flush=True)
                        break

        # Use preset's default reference image if configured
        if not ref_image_url and _preset.default_ref_image:
            ref_image_url = _preset.default_ref_image
            print(f"[Pipeline] Using preset default reference image", flush=True)

        # Generate new reference image only if we don't have one. Track
        # whether THIS run is the one that generated it — the prompt is only
        # trustworthy as this image's appearance if it's the prompt that
        # actually produced these pixels, not a fresh, non-deterministic
        # rewrite from a rerun's ScriptGenerator call.
        char_prompt = None
        image_generated_this_run = False
        if not ref_image_url:
            char_prompt = script_result.get("character_image_prompt")
            if char_prompt:
                ref_image_url = deps.image_generator().generate(char_prompt)
                image_generated_this_run = True
                print("[Pipeline] New reference image generated", flush=True)

        # Save reference image URL to sheet for future parts (buffered). The
        # prompt that produced it rides along in the same write, as
        # character_appearance, only when this run generated the image — so
        # the pair can never drift apart. A rerun that reuses a saved URL
        # must read the words that actually match it, not whatever
        # ScriptGenerator invents that day.
        if ref_image_url:
            if image_generated_this_run:
                ledger.record(row_index, ref_image_url=ref_image_url, character_appearance=char_prompt)
            else:
                ledger.record(row_index, ref_image_url=ref_image_url)

        # Per-shot storyboard generation. Opt-in per preset via
        # `per_shot_storyboards: True` in config. For each shot, GPT Image 2
        # Edit takes the reference image as the base and the shot's scene
        # description as the prompt, producing a shot-appropriate first frame
        # that preserves the character's identity. Solves wallpaper-effect
        # and character drift across shots.
        #
        # With `chain_reference_frames: True` the storyboards are generated
        # lazily, one per shot, each also seeing the previous shot's last
        # frame — so identity carries forward from what actually rendered.

        # The locked appearance, in words. The reference image alone loses the
        # costume: the edit prompt describes the scene richly and the character
        # only in pixels, and the model resolves that conflict toward the text.
        # The rule is one sentence: use the words that describe the image
        # actually in hand. Priority: the canon locked paragraph (form-aware,
        # beats everything); else, if THIS run generated the reference image,
        # the prompt that produced it — a fresh image always gets fresh
        # words, never a saved description of a different, earlier image;
        # else the appearance saved alongside whatever image IS in hand — the
        # series part's, when the image was reused from an earlier part,
        # otherwise this row's own saved value.
        appearance: str | None = None
        if _preset.serialized_canon:
            appearance = chars.get_main_appearance_for_form(form)
        if not appearance and image_generated_this_run:
            appearance = char_prompt
        if not appearance:
            appearance = series_appearance or (str(episode.character_appearance).strip() or None)

        storyboard_urls: list[str | None] | None = None
        storyboard_supplier = None
        if _preset.per_shot_storyboards and ref_image_url:
            if _preset.chain_reference_frames:
                storyboard_supplier = deps.chained_storyboards(
                    ref_image_url, style=VIDEO_STYLE, appearance=appearance,
                )
                print("[Pipeline] Chained storyboards enabled", flush=True)
            else:
                storyboard_urls = deps.storyboards(
                    script_result["shots"], ref_image_url,
                    style=VIDEO_STYLE, appearance=appearance,
                )

        video_path = deps.video_producer().produce(
            script_result["shots"],
            reference_image_url=ref_image_url,
            storyboard_urls=storyboard_urls,
            storyboard_supplier=storyboard_supplier,
        )

        # Audio mix routing:
        # 1. Preset configures `audio_mix.mode = "narration_over_native"` →
        #    layer ElevenLabs narration over Seedance's native audio (preset-7).
        # 2. VIDEO_PROVIDER=atlas without that config → use Seedance native only.
        # 3. Other providers → full ElevenLabs voiceover + BGM (legacy v1 path).
        audio_mix_cfg = _preset.audio_mix or {}
        audio_mode = audio_mix_cfg.get("mode")

        if audio_mode == "native_only":
            # No voiceover at all — the model's own audio is the soundtrack.
            # The file is passed through untouched rather than re-encoded at
            # volume 1.0, so nothing is lost to a needless transcode.
            final_path = video_path
            print("[Pipeline] Native audio only — no narration, no re-encode", flush=True)
        elif audio_mode == "narration_over_native":
            # Auto-derive title/end card durations so narration stays inside
            # the story segment (doesn't overlap brand container audio stings)
            title_duration = _preset.title_card_duration
            end_duration = _preset.end_card_duration
            final_path = deps.audio_mixer().mix_with_native_audio(
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
            final_path = deps.audio_mixer().mix(video_path, script_result["narrative"], episode.genre)

        # Format YouTube title.
        # Preset-7 (Zenith): "The Chronicle of Zenith — Ep {N}: {Episode Title}"
        # Other series presets: "Series Title: Episode Title - Part N"
        numbered_title = _preset.format_youtube_title(
            script_result["title"], episode.episode_number
        )
        if numbered_title:
            script_result["title"] = numbered_title
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
        youtube_url = deps.uploader().upload(final_path, script_result)

        ledger.finish(row_index, youtube_url)
        return {"status": "done", "youtube_url": youtube_url}

    except Exception as exc:
        try:
            ledger.fail(row_index, str(exc))
        except Exception:
            pass
        raise
