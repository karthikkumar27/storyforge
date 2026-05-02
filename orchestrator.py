from config import STORY_MODE, VIDEO_PROVIDER, ACTIVE_PRESET, GENRES, _preset
from modules.gsheet_reader import GSheetReader, get_episode_reader
from modules.brief_generator import BriefGenerator
from modules.script_generator import ScriptGenerator
from modules.image_generator import create_image_generator
from modules.video_producer import create_video_producer
from modules.audio_mixer import AudioMixer
from modules.youtube_uploader import YouTubeUploader


def run_pipeline() -> dict:
    # Routes to ALAN_STORY sheet for preset-7, main GOOGLE_SHEET for everything else
    reader = get_episode_reader()
    row = reader.get_pending_row()

    if not row:
        previous_parts = []
        past_stories = reader.get_past_stories(limit=20)
        print(f"[Pipeline] {len(past_stories)} past stories loaded for anti-repetition", flush=True)

        if STORY_MODE == "series":
            series_id = reader.get_latest_incomplete_series()
            if series_id:
                previous_parts = reader.get_series_parts(series_id)
                print(f"[Pipeline] Continuing series {series_id}, part {len(previous_parts) + 1}", flush=True)
            else:
                print("[Pipeline] Starting new series", flush=True)

        # For preset-7 (200-episode continuous series), compute the next absolute
        # episode number across the entire series so brief_generator can resolve
        # the matching arc context.
        episode_number = None
        if ACTIVE_PRESET == "preset-7":
            episode_number = reader.get_next_episode_number(GENRES)
            print(f"[Pipeline] Preset-7 — generating episode #{episode_number}", flush=True)

        brief_data = BriefGenerator().generate(
            previous_parts=previous_parts,
            past_stories=past_stories,
            episode_number=episode_number,
        )
        reader.append_pending_row(brief_data)
        row = reader.get_pending_row()

    if not row:
        return {"status": "no_pending_rows"}

    row_index = row["row_index"]

    try:
        reader.update_status(row_index, "generating")

        script_result = ScriptGenerator().generate(row["story_brief"], row["genre"])
        reader.update_script(row_index, script_result["narrative"])

        ref_image_url = None

        # Preset-7 — form-aware lookup from the characters sheet (Alan vs Zenith).
        # This takes priority over legacy series-id reuse and preset defaults so
        # each episode uses the right form's locked image.
        if ACTIVE_PRESET == "preset-7":
            from modules.characters_reader import CharactersReader
            chars = CharactersReader()
            form = str(row.get("character_form", "")).strip().lower() or "normal"
            ref_image_url = chars.get_main_ref_image_for_form(form)
            if ref_image_url:
                print(f"[Pipeline] Preset-7 character_form={form} → locked ref image from characters sheet", flush=True)
            else:
                print(f"[Pipeline] Preset-7 character_form={form} but no locked ref image yet — will generate fresh", flush=True)

        # Reuse reference image from Part 1 if this is a series continuation (other presets)
        if not ref_image_url and STORY_MODE == "series":
            series_id = reader.get_latest_incomplete_series()
            if series_id:
                parts = reader.get_series_parts(series_id)
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

        # Save reference image URL to sheet for future parts
        if ref_image_url:
            reader.update_ref_image(row_index, ref_image_url)

        # Premium: per-shot storyboard generation for preset-7.
        # For each shot, GPT Image 2 Edit takes the locked character reference as
        # the base and the shot's scene description as the prompt, producing a
        # shot-appropriate first frame that preserves the character's identity.
        # This solves both wallpaper-effect and character drift.
        storyboard_urls: list[str | None] | None = None
        if ACTIVE_PRESET == "preset-7" and ref_image_url:
            storyboard_urls = []
            shots = script_result["shots"]
            print(f"[Pipeline] Generating {len(shots)} per-shot storyboards (Premium)...", flush=True)
            from modules.image_generator import AtlasImageGenerator
            edit_gen = AtlasImageGenerator()
            for i, shot_prompt in enumerate(shots):
                # Wrap the shot prompt so GPT Image 2 Edit produces a still that
                # matches the START of that shot's action (not the action itself).
                edit_prompt = (
                    f"Same character as in the reference image — same face, same hair, same outfit, "
                    f"same anime cel-shaded illustration style. Now show this exact character at the "
                    f"START of this scene as a 9:16 vertical still frame, no motion blur, no other "
                    f"characters in frame: {shot_prompt}"
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

        # Atlas provider has native audio (Seedance generate_audio), skip ElevenLabs
        if VIDEO_PROVIDER == "atlas":
            final_path = video_path
            print("[Pipeline] Using Seedance native audio, skipping ElevenLabs", flush=True)
        else:
            final_path = AudioMixer().mix(video_path, script_result["narrative"], row["genre"])

        # Format YouTube title.
        # Preset-7 (Zenith): "The Chronicle of Zenith — Ep {N}: {Episode Title}"
        # Other series presets: "Series Title: Episode Title - Part N"
        if ACTIVE_PRESET == "preset-7" and row.get("episode_number"):
            ep_n = row["episode_number"]
            episode_title = script_result["title"]
            script_result["title"] = f"The Chronicle of Zenith — Ep {ep_n}: {episode_title}"
            print(f"[Pipeline] YouTube title: {script_result['title']}", flush=True)
        elif row.get("story_mode") == "series" and row.get("part_number"):
            part_num = row["part_number"]
            episode_title = script_result["title"]
            # Get series title from Part 1
            series_id = row.get("series_id", "")
            series_title = episode_title  # fallback
            if series_id:
                parts = reader.get_series_parts(series_id)
                if parts:
                    series_title = parts[0].get("title", episode_title)
            if str(part_num) == "1":
                script_result["title"] = f"{episode_title} - Part 1"
            else:
                script_result["title"] = f"{series_title}: {episode_title} - Part {part_num}"
            print(f"[Pipeline] YouTube title: {script_result['title']}", flush=True)

        reader.update_status(row_index, "uploading")
        youtube_url = YouTubeUploader().upload(final_path, script_result)

        reader.update_done(row_index, youtube_url)
        return {"status": "done", "youtube_url": youtube_url}

    except Exception as exc:
        try:
            reader.update_error(row_index, str(exc))
        except Exception:
            pass
        raise
