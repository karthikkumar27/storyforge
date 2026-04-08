from modules.gsheet_reader import GSheetReader
from modules.script_generator import ScriptGenerator
from modules.video_producer import VideoProducer
from modules.audio_mixer import AudioMixer
from modules.youtube_uploader import YouTubeUploader


def run_pipeline() -> dict:
    reader = GSheetReader()
    row = reader.get_pending_row()
    if not row:
        return {"status": "no_pending_rows"}

    row_index = row["row_index"]
    reader.update_status(row_index, "generating")

    try:
        script_result = ScriptGenerator().generate(row["story_brief"], row["genre"])
        reader.update_script(row_index, script_result["narrative"])

        video_path = VideoProducer().produce(script_result["shots"])
        final_path = AudioMixer().mix(video_path, script_result["narrative"], row["genre"])

        reader.update_status(row_index, "uploading")
        youtube_url = YouTubeUploader().upload(final_path, script_result)

        reader.update_done(row_index, youtube_url)
        return {"status": "done", "youtube_url": youtube_url}

    except Exception as exc:
        reader.update_error(row_index, str(exc))
        raise
