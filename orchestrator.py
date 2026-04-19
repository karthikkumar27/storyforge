from config import STORY_MODE
from modules.gsheet_reader import GSheetReader
from modules.brief_generator import BriefGenerator
from modules.script_generator import ScriptGenerator
from modules.image_generator import ReferenceImageGenerator
from modules.video_producer import create_video_producer
from modules.audio_mixer import AudioMixer
from modules.youtube_uploader import YouTubeUploader


def run_pipeline() -> dict:
    reader = GSheetReader()
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

        brief_data = BriefGenerator().generate(previous_parts, past_stories)
        reader.append_pending_row(brief_data)
        row = reader.get_pending_row()

    if not row:
        return {"status": "no_pending_rows"}

    row_index = row["row_index"]

    try:
        reader.update_status(row_index, "generating")

        script_result = ScriptGenerator().generate(row["story_brief"], row["genre"])
        reader.update_script(row_index, script_result["narrative"])

        # Reuse reference image from Part 1 if this is a series continuation
        ref_image_url = None
        if STORY_MODE == "series":
            series_id = reader.get_latest_incomplete_series()
            if series_id:
                parts = reader.get_series_parts(series_id)
                for part in parts:
                    url = part.get("ref_image_url", "")
                    if url:
                        ref_image_url = url
                        print(f"[Pipeline] Reusing reference image from Part {part.get('part_number', '?')}", flush=True)
                        break

        # Generate new reference image only if we don't have one from a previous part
        if not ref_image_url:
            char_prompt = script_result.get("character_image_prompt")
            if char_prompt:
                ref_image_url = ReferenceImageGenerator().generate(char_prompt)
                print("[Pipeline] New reference image generated", flush=True)

        # Save reference image URL to sheet for future parts
        if ref_image_url:
            reader.update_ref_image(row_index, ref_image_url)

        video_path = create_video_producer().produce(script_result["shots"], ref_image_url)
        final_path = AudioMixer().mix(video_path, script_result["narrative"], row["genre"])

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
