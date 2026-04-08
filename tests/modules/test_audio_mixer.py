# tests/modules/test_audio_mixer.py
import pytest
from unittest.mock import MagicMock, patch


@patch("modules.audio_mixer.httpx")
def test_voiceover_uses_adam_for_scifi(mock_httpx, monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")

    mock_resp = MagicMock()
    mock_resp.content = b"fake_mp3_bytes"
    mock_httpx.post.return_value = mock_resp

    from modules.audio_mixer import AudioMixer
    mixer = AudioMixer()

    with patch("modules.audio_mixer.tempfile.mkdtemp", return_value=str(tmp_path)):
        mixer._generate_voiceover("In the void between stars...", "sci-fi")

    call_url = mock_httpx.post.call_args[0][0]
    assert "pNInz6obpgDQGcFmaJgB" in call_url  # Adam


@patch("modules.audio_mixer.httpx")
def test_voiceover_uses_arnold_for_horror(mock_httpx, monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")

    mock_resp = MagicMock()
    mock_resp.content = b"fake_mp3_bytes"
    mock_httpx.post.return_value = mock_resp

    from modules.audio_mixer import AudioMixer
    mixer = AudioMixer()

    with patch("modules.audio_mixer.tempfile.mkdtemp", return_value=str(tmp_path)):
        mixer._generate_voiceover("Something dark lurks...", "horror")

    call_url = mock_httpx.post.call_args[0][0]
    assert "VR6AewLTigWG4xSOukaG" in call_url  # Arnold


@patch("modules.audio_mixer.subprocess.run")
@patch("modules.audio_mixer.AudioMixer._generate_voiceover")
def test_mix_calls_ffmpeg_with_video_voiceover_and_music(
    mock_voiceover, mock_run, monkeypatch, tmp_path
):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")
    mock_voiceover.return_value = str(tmp_path / "voiceover.mp3")

    from modules.audio_mixer import AudioMixer
    mixer = AudioMixer()
    video_path = str(tmp_path / "stitched.mp4")
    mixer.mix(video_path, "narrative text", "sci-fi")

    args = mock_run.call_args[0][0]
    assert args[0] == "ffmpeg"
    assert video_path in args
    assert str(tmp_path / "voiceover.mp3") in args
    assert "assets/music/sci-fi.mp3" in args


@patch("modules.audio_mixer.subprocess.run")
@patch("modules.audio_mixer.AudioMixer._generate_voiceover")
def test_mix_output_path_is_final_mp4(mock_voiceover, mock_run, monkeypatch, tmp_path):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "el-key")
    mock_voiceover.return_value = str(tmp_path / "voiceover.mp3")

    from modules.audio_mixer import AudioMixer
    mixer = AudioMixer()
    video_path = str(tmp_path / "stitched.mp4")
    output = mixer.mix(video_path, "narrative", "horror")

    assert output == str(tmp_path / "final.mp4")
