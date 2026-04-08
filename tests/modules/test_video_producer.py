# tests/modules/test_video_producer.py
import pytest
from unittest.mock import MagicMock, patch, call


@patch("modules.video_producer.httpx")
def test_submit_shot_returns_task_id(mock_httpx, monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"task_id": "task_abc"}}
    mock_httpx.post.return_value = mock_resp

    from modules.video_producer import VideoProducer
    producer = VideoProducer()
    task_id = producer._submit_shot("Slow orbital pan, deep space black, nebula glow")

    assert task_id == "task_abc"
    mock_httpx.post.assert_called_once()


@patch("modules.video_producer.httpx")
def test_poll_shot_returns_url_when_succeed(mock_httpx, monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "data": {"task_status": "succeed", "videos": [{"url": "https://cdn.kling.ai/v.mp4"}]}
    }
    mock_httpx.get.return_value = mock_resp

    from modules.video_producer import VideoProducer
    producer = VideoProducer()
    url = producer._poll_shot("task_abc")

    assert url == "https://cdn.kling.ai/v.mp4"


@patch("modules.video_producer.httpx")
def test_poll_shot_raises_on_failed_status(mock_httpx, monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {"task_status": "failed"}}
    mock_httpx.get.return_value = mock_resp

    from modules.video_producer import VideoProducer
    producer = VideoProducer()

    with pytest.raises(RuntimeError, match="failed"):
        producer._poll_shot("task_abc")


@patch("modules.video_producer.subprocess.run")
def test_stitch_writes_concat_file_and_calls_ffmpeg(mock_run, monkeypatch, tmp_path):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "key123")
    monkeypatch.setenv("KLING_SECRET_KEY", "secret456")

    from modules.video_producer import VideoProducer
    producer = VideoProducer()
    clip_paths = [str(tmp_path / "shot_00.mp4"), str(tmp_path / "shot_01.mp4")]
    output = str(tmp_path / "stitched.mp4")

    producer._stitch(clip_paths, output)

    args = mock_run.call_args[0][0]
    assert args[0] == "ffmpeg"
    assert "-f" in args
    assert "concat" in args
    assert output in args


def test_jwt_token_contains_access_key_id(monkeypatch):
    monkeypatch.setenv("KLING_ACCESS_KEY_ID", "my_key_id")
    monkeypatch.setenv("KLING_SECRET_KEY", "my_secret")

    from modules.video_producer import VideoProducer
    import jwt

    producer = VideoProducer()
    token = producer._jwt_token()
    decoded = jwt.decode(token, "my_secret", algorithms=["HS256"])

    assert decoded["iss"] == "my_key_id"
