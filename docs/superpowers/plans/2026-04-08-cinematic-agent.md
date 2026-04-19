# Cinematic AI Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily automated pipeline that reads a story brief from Google Sheets, generates a cinematic sci-fi/horror/space video using Claude + Kling AI + ElevenLabs, and uploads it to YouTube.

**Architecture:** Modular Python pipeline with 5 independent modules (gsheet_reader, script_generator, video_producer, audio_mixer, youtube_uploader) coordinated by an orchestrator. Runs as a GCP Cloud Run container triggered daily at 10:00 PM UTC+8 via Cloud Scheduler.

**Tech Stack:** Python 3.11, Flask, anthropic SDK, gspread, httpx, PyJWT, ElevenLabs REST API, YouTube Data API v3, ffmpeg (in Docker), pytest + unittest.mock

---

## File Map

| File | Purpose |
|------|---------|
| `config.py` | All constants: API base URLs, voice IDs, music paths, model names |
| `modules/__init__.py` | Empty — marks modules as a package |
| `modules/gsheet_reader.py` | Read pending rows, update status/script/done/error |
| `modules/script_generator.py` | Claude API — generate narrative + shot prompts |
| `modules/video_producer.py` | Kling API — submit shots, poll, download, ffmpeg stitch |
| `modules/audio_mixer.py` | ElevenLabs voiceover + ffmpeg audio mix |
| `modules/youtube_uploader.py` | YouTube Data API v3 upload |
| `orchestrator.py` | Coordinate all modules, propagate errors to GSheet |
| `main.py` | Flask HTTP entrypoint for Cloud Run |
| `discovery.py` | Manual tool — search/score/auto-select AI video tools |
| `Dockerfile` | Python 3.11 + ffmpeg |
| `requirements.txt` | Pinned dependencies |
| `.env.example` | Template for local development |
| `tests/modules/test_gsheet_reader.py` | GSheetReader unit tests |
| `tests/modules/test_script_generator.py` | ScriptGenerator unit tests |
| `tests/modules/test_video_producer.py` | VideoProducer unit tests |
| `tests/modules/test_audio_mixer.py` | AudioMixer unit tests |
| `tests/modules/test_youtube_uploader.py` | YouTubeUploader unit tests |
| `tests/test_orchestrator.py` | Orchestrator integration tests |
| `tests/test_main.py` | Flask endpoint tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `modules/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/modules/__init__.py`

- [ ] **Step 1: Create `requirements.txt`**

```
anthropic==0.34.2
gspread==6.1.2
google-auth==2.29.0
google-api-python-client==2.127.0
google-auth-oauthlib==1.2.0
httpx==0.27.0
PyJWT==2.8.0
flask==3.0.3
python-dotenv==1.0.1
pytest==8.2.0
pytest-mock==3.14.0
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Kling AI — from klingai.com developer console
KLING_ACCESS_KEY_ID=your_access_key_id_here
KLING_SECRET_KEY=your_secret_key_here

# ElevenLabs — from elevenlabs.io
ELEVENLABS_API_KEY=your_elevenlabs_key_here

# Google Sheets — JSON content of service account key file
GOOGLE_SHEETS_CREDENTIALS={"type":"service_account",...}
GOOGLE_SHEET_ID=your_spreadsheet_id_here

# YouTube OAuth2
YOUTUBE_CLIENT_ID=your_client_id_here
YOUTUBE_CLIENT_SECRET=your_client_secret_here
YOUTUBE_OAUTH_TOKEN={"refresh_token":"your_refresh_token_here"}

# Claude
ANTHROPIC_API_KEY=your_anthropic_key_here
```

- [ ] **Step 3: Create `config.py`**

```python
# Kling AI
KLING_BASE_URL = "https://api.klingai.com"
KLING_MODEL = "kling-v1"
SHOT_DURATION = "10"
ASPECT_RATIO = "16:9"
SHOTS_COUNT = 7
POLL_INTERVAL_SEC = 10
MAX_POLL_ATTEMPTS = 60

# ElevenLabs voice IDs
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
VOICE_MAP = {
    "sci-fi": "pNInz6obpgDQGcFmaJgB",   # Adam
    "horror": "VR6AewLTigWG4xSOukaG",   # Arnold
    "space":  "ErXwobaYiN019PkySvjV",   # Antoni
    "blend":  "ErXwobaYiN019PkySvjV",   # Antoni
}

# Bundled royalty-free music
MUSIC_MAP = {
    "sci-fi": "assets/music/sci-fi.mp3",
    "horror": "assets/music/horror.mp3",
    "space":  "assets/music/space.mp3",
    "blend":  "assets/music/space.mp3",
}

# Claude
CLAUDE_MODEL = "claude-opus-4-6"

# YouTube
YOUTUBE_CATEGORY_ID = "24"   # Entertainment
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
```

- [ ] **Step 4: Create empty `__init__.py` files**

```bash
touch modules/__init__.py tests/__init__.py tests/modules/__init__.py
```

- [ ] **Step 5: Create `assets/music/` placeholder directory**

```bash
mkdir -p assets/music
# Download or add 3 royalty-free MP3 files:
# assets/music/sci-fi.mp3   (ambient electronic)
# assets/music/horror.mp3   (dark atmospheric)
# assets/music/space.mp3    (deep space ambient)
# Sources: freemusicarchive.org, pixabay.com/music (CC0 license)
```

- [ ] **Step 6: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install without errors

- [ ] **Step 7: Commit**

```bash
git init
git add requirements.txt .env.example config.py modules/__init__.py tests/__init__.py tests/modules/__init__.py
git commit -m "feat: project scaffolding — config, deps, structure"
```

---

## Task 2: GSheet Reader Module

**Files:**
- Create: `modules/gsheet_reader.py`
- Create: `tests/modules/test_gsheet_reader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/modules/test_gsheet_reader.py
import json
import pytest
from unittest.mock import MagicMock, patch


@patch("modules.gsheet_reader.gspread")
@patch("modules.gsheet_reader.Credentials")
def test_get_pending_row_returns_first_pending(mock_creds, mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"title": "Test", "story_brief": "A spaceship drifts", "genre": "sci-fi",
         "duration_sec": 75, "status": "pending"},
    ]
    mock_gspread.authorize.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    row = reader.get_pending_row()

    assert row["story_brief"] == "A spaceship drifts"
    assert row["genre"] == "sci-fi"
    assert row["row_index"] == 2


@patch("modules.gsheet_reader.gspread")
@patch("modules.gsheet_reader.Credentials")
def test_get_pending_row_skips_done_rows(mock_creds, mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"title": "Old", "story_brief": "Old story", "genre": "blend",
         "duration_sec": 75, "status": "done"},
        {"title": "New", "story_brief": "New idea", "genre": "horror",
         "duration_sec": 75, "status": "pending"},
    ]
    mock_gspread.authorize.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    row = reader.get_pending_row()

    assert row["story_brief"] == "New idea"
    assert row["row_index"] == 3


@patch("modules.gsheet_reader.gspread")
@patch("modules.gsheet_reader.Credentials")
def test_get_pending_row_returns_none_when_all_done(mock_creds, mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.get_all_records.return_value = [
        {"title": "Done", "story_brief": "Old", "genre": "sci-fi",
         "duration_sec": 75, "status": "done"},
    ]
    mock_gspread.authorize.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    assert reader.get_pending_row() is None


@patch("modules.gsheet_reader.gspread")
@patch("modules.gsheet_reader.Credentials")
def test_update_status_writes_correct_cell(mock_creds, mock_gspread, monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEETS_CREDENTIALS", json.dumps({"type": "service_account"}))
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet123")

    mock_sheet = MagicMock()
    mock_sheet.row_values.return_value = [
        "title", "story_brief", "script_text", "genre", "duration_sec",
        "status", "youtube_url", "error_msg"
    ]
    mock_gspread.authorize.return_value.open_by_key.return_value.sheet1 = mock_sheet

    from modules.gsheet_reader import GSheetReader
    reader = GSheetReader()
    reader.update_status(2, "generating")

    mock_sheet.update_cell.assert_called_with(2, 6, "generating")  # status is col 6
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/modules/test_gsheet_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'modules.gsheet_reader'`

- [ ] **Step 3: Implement `modules/gsheet_reader.py`**

```python
import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class GSheetReader:
    def __init__(self):
        creds_json = os.environ["GOOGLE_SHEETS_CREDENTIALS"]
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        gc = gspread.authorize(creds)
        sheet_id = os.environ["GOOGLE_SHEET_ID"]
        self.sheet = gc.open_by_key(sheet_id).sheet1

    def get_pending_row(self) -> dict | None:
        records = self.sheet.get_all_records()
        for i, row in enumerate(records, start=2):
            if row.get("status") == "pending":
                return {
                    "row_index": i,
                    "title": row.get("title", ""),
                    "story_brief": row["story_brief"],
                    "genre": row.get("genre", "blend"),
                    "duration_sec": int(row.get("duration_sec", 75)),
                }
        return None

    def update_status(self, row_index: int, status: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), status)

    def update_script(self, row_index: int, script_text: str) -> None:
        self.sheet.update_cell(row_index, self._col("script_text"), script_text)

    def update_done(self, row_index: int, youtube_url: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), "done")
        self.sheet.update_cell(row_index, self._col("youtube_url"), youtube_url)

    def update_error(self, row_index: int, error_msg: str) -> None:
        self.sheet.update_cell(row_index, self._col("status"), "error")
        self.sheet.update_cell(row_index, self._col("error_msg"), error_msg)

    def _col(self, name: str) -> int:
        headers = self.sheet.row_values(1)
        return headers.index(name) + 1
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/modules/test_gsheet_reader.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add modules/gsheet_reader.py tests/modules/test_gsheet_reader.py
git commit -m "feat: gsheet reader module with status tracking"
```

---

## Task 3: Script Generator Module

**Files:**
- Create: `modules/script_generator.py`
- Create: `tests/modules/test_script_generator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/modules/test_script_generator.py
import json
import pytest
from unittest.mock import MagicMock, patch

SAMPLE_RESPONSE = {
    "narrative": "In the void between stars, a signal pulses...",
    "title": "The Last Signal",
    "description": "A haunting journey through deep space where silence speaks louder than fear.",
    "tags": ["scifi", "space", "horror", "cinematic", "shortfilm"],
    "shots": [
        "Slow orbital pan around a derelict space station, deep space black, distant nebula glow.",
        "Interior corridor, emergency red lighting flickers, dust particles float in zero-g.",
        "Close-up of cracked helmet visor reflecting a dying star.",
        "Wide dolly push through an airlock, cold blue light bleeds in from outside.",
        "Extreme close-up of a blinking distress beacon, pulse slowing.",
        "Pull back reveal: massive alien monolith drifts behind the station.",
        "Final wide shot: the station, the monolith, silence and stars.",
    ],
}


@patch("modules.script_generator.anthropic.Anthropic")
def test_generate_returns_parsed_dict(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(SAMPLE_RESPONSE))
    ]

    from modules.script_generator import ScriptGenerator
    gen = ScriptGenerator()
    result = gen.generate("A ghost astronaut haunts an abandoned station", "blend")

    assert result["narrative"] == "In the void between stars, a signal pulses..."
    assert len(result["shots"]) == 7
    assert result["title"] == "The Last Signal"
    assert "tags" in result
    assert "description" in result


@patch("modules.script_generator.anthropic.Anthropic")
def test_generate_passes_genre_and_brief_to_claude(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(SAMPLE_RESPONSE))
    ]

    from modules.script_generator import ScriptGenerator
    gen = ScriptGenerator()
    gen.generate("A lost probe sends back alien signals", "sci-fi")

    call_kwargs = mock_client.messages.create.call_args.kwargs
    user_content = call_kwargs["messages"][0]["content"]
    assert "sci-fi" in user_content
    assert "A lost probe sends back alien signals" in user_content


@patch("modules.script_generator.anthropic.Anthropic")
def test_generate_raises_on_invalid_json(mock_anthropic_class, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_client = MagicMock()
    mock_anthropic_class.return_value = mock_client
    mock_client.messages.create.return_value.content = [
        MagicMock(text="not valid json at all")
    ]

    from modules.script_generator import ScriptGenerator
    gen = ScriptGenerator()

    with pytest.raises(json.JSONDecodeError):
        gen.generate("brief", "sci-fi")
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/modules/test_script_generator.py -v
```

Expected: `ModuleNotFoundError: No module named 'modules.script_generator'`

- [ ] **Step 3: Implement `modules/script_generator.py`**

```python
import os
import json
import anthropic
from config import CLAUDE_MODEL, SHOTS_COUNT

SYSTEM_PROMPT = """You are a cinematic script writer specializing in sci-fi, outer space, and subtle horror.
Write short-form cinematic scripts for AI video generation.

Your output MUST be valid JSON with exactly this structure:
{
  "narrative": "Full readable narrative script (200-400 words)",
  "title": "Compelling video title (max 70 chars)",
  "description": "YouTube description (100-150 words, includes genre mood)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "shots": [
    "Shot 1: detailed cinematic description for AI video generation",
    ...
  ]
}

Shot prompt rules:
- 1-2 sentences per shot, highly specific
- Include camera movement: slow pan, dolly push, orbital shot, handheld drift, etc.
- Include lighting/atmosphere: deep space black, nebula glow, cold blue light, etc.
- Each shot = ~10 seconds of content
- Optimized for Kling AI text-to-video generation
- No dialogue or text overlays — visual storytelling only

Return JSON only. No markdown fences, no explanation."""


class ScriptGenerator:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, story_brief: str, genre: str) -> dict:
        prompt = (
            f"Genre: {genre}\n"
            f"Story brief: {story_brief}\n\n"
            f"Generate a {SHOTS_COUNT}-shot cinematic script. Return valid JSON only."
        )
        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        return json.loads(raw)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/modules/test_script_generator.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add modules/script_generator.py tests/modules/test_script_generator.py
git commit -m "feat: script generator — Claude generates narrative + shot prompts"
```

---

## Task 4: Video Producer Module

**Files:**
- Create: `modules/video_producer.py`
- Create: `tests/modules/test_video_producer.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/modules/test_video_producer.py -v
```

Expected: `ModuleNotFoundError: No module named 'modules.video_producer'`

- [ ] **Step 3: Implement `modules/video_producer.py`**

```python
import os
import time
import subprocess
import tempfile

import httpx
import jwt

from config import (
    KLING_BASE_URL, KLING_MODEL, SHOT_DURATION, ASPECT_RATIO,
    POLL_INTERVAL_SEC, MAX_POLL_ATTEMPTS,
)


class VideoProducer:
    def __init__(self):
        self.access_key_id = os.environ["KLING_ACCESS_KEY_ID"]
        self.secret_key = os.environ["KLING_SECRET_KEY"]

    def _jwt_token(self) -> str:
        now = int(time.time())
        payload = {"iss": self.access_key_id, "exp": now + 1800, "nbf": now - 5}
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._jwt_token()}",
            "Content-Type": "application/json",
        }

    def _submit_shot(self, prompt: str) -> str:
        resp = httpx.post(
            f"{KLING_BASE_URL}/v1/videos/text2video",
            headers=self._headers(),
            json={"model": KLING_MODEL, "prompt": prompt,
                  "duration": SHOT_DURATION, "aspect_ratio": ASPECT_RATIO},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["task_id"]

    def _poll_shot(self, task_id: str) -> str:
        for _ in range(MAX_POLL_ATTEMPTS):
            resp = httpx.get(
                f"{KLING_BASE_URL}/v1/videos/text2video/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if data["task_status"] == "succeed":
                return data["videos"][0]["url"]
            if data["task_status"] == "failed":
                raise RuntimeError(f"Kling task {task_id} failed")
            time.sleep(POLL_INTERVAL_SEC)
        raise TimeoutError(f"Kling task {task_id} timed out after {MAX_POLL_ATTEMPTS} polls")

    def _download_clip(self, url: str, path: str) -> None:
        with httpx.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)

    def _stitch(self, clip_paths: list[str], output_path: str) -> None:
        concat_file = os.path.join(os.path.dirname(output_path), "concat.txt")
        with open(concat_file, "w") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        subprocess.run(
            ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file,
             "-c", "copy", output_path, "-y"],
            check=True,
            capture_output=True,
        )

    def produce(self, shots: list[str]) -> str:
        workdir = tempfile.mkdtemp(prefix="cinematic_")
        clip_paths = []
        for i, prompt in enumerate(shots):
            task_id = self._submit_shot(prompt)
            video_url = self._poll_shot(task_id)
            clip_path = os.path.join(workdir, f"shot_{i:02d}.mp4")
            self._download_clip(video_url, clip_path)
            clip_paths.append(clip_path)
        output_path = os.path.join(workdir, "stitched.mp4")
        self._stitch(clip_paths, output_path)
        return output_path
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/modules/test_video_producer.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add modules/video_producer.py tests/modules/test_video_producer.py
git commit -m "feat: video producer — Kling API + JWT auth + ffmpeg stitch"
```

---

## Task 5: Audio Mixer Module

**Files:**
- Create: `modules/audio_mixer.py`
- Create: `tests/modules/test_audio_mixer.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/modules/test_audio_mixer.py -v
```

Expected: `ModuleNotFoundError: No module named 'modules.audio_mixer'`

- [ ] **Step 3: Implement `modules/audio_mixer.py`**

```python
import os
import subprocess
import tempfile

import httpx

from config import ELEVENLABS_BASE_URL, VOICE_MAP, MUSIC_MAP


class AudioMixer:
    def __init__(self):
        self.api_key = os.environ["ELEVENLABS_API_KEY"]

    def _generate_voiceover(self, narrative: str, genre: str) -> str:
        voice_id = VOICE_MAP.get(genre, VOICE_MAP["blend"])
        resp = httpx.post(
            f"{ELEVENLABS_BASE_URL}/text-to-speech/{voice_id}",
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            json={
                "text": narrative,
                "model_id": "eleven_monolingual_v1",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            timeout=60,
        )
        resp.raise_for_status()
        workdir = tempfile.mkdtemp(prefix="audio_")
        vo_path = os.path.join(workdir, "voiceover.mp3")
        with open(vo_path, "wb") as f:
            f.write(resp.content)
        return vo_path

    def mix(self, video_path: str, narrative: str, genre: str) -> str:
        voiceover_path = self._generate_voiceover(narrative, genre)
        music_path = MUSIC_MAP.get(genre, MUSIC_MAP["blend"])
        output_path = video_path.replace("stitched.mp4", "final.mp4")
        subprocess.run(
            [
                "ffmpeg",
                "-i", video_path,
                "-i", voiceover_path,
                "-i", music_path,
                "-filter_complex",
                "[1:a]volume=1.0[vo];[2:a]volume=0.3[bg];[vo][bg]amix=inputs=2:duration=first[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                output_path,
                "-y",
            ],
            check=True,
            capture_output=True,
        )
        return output_path
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/modules/test_audio_mixer.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add modules/audio_mixer.py tests/modules/test_audio_mixer.py
git commit -m "feat: audio mixer — ElevenLabs voiceover + genre-adaptive voice + ffmpeg mix"
```

---

## Task 6: YouTube Uploader Module

**Files:**
- Create: `modules/youtube_uploader.py`
- Create: `tests/modules/test_youtube_uploader.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/modules/test_youtube_uploader.py
import json
import pytest
from unittest.mock import MagicMock, patch

SCRIPT_RESULT = {
    "title": "The Last Signal",
    "description": "A haunting journey through deep space.",
    "tags": ["scifi", "space", "horror", "cinematic", "shortfilm"],
    "narrative": "In the void...",
    "shots": [],
}


@patch("modules.youtube_uploader.MediaFileUpload")
@patch("modules.youtube_uploader.build")
@patch("modules.youtube_uploader.Credentials")
@patch("modules.youtube_uploader.Request")
def test_upload_returns_youtube_url(
    mock_request, mock_creds_class, mock_build, mock_media, monkeypatch
):
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN", json.dumps({"refresh_token": "tok123"}))
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client_id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client_secret")

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds_class.return_value = mock_creds

    mock_youtube = MagicMock()
    mock_build.return_value = mock_youtube

    mock_insert_request = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_insert_request
    mock_insert_request.next_chunk.return_value = (None, {"id": "abc123"})

    from modules.youtube_uploader import YouTubeUploader
    uploader = YouTubeUploader()
    url = uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    assert url == "https://www.youtube.com/watch?v=abc123"


@patch("modules.youtube_uploader.MediaFileUpload")
@patch("modules.youtube_uploader.build")
@patch("modules.youtube_uploader.Credentials")
@patch("modules.youtube_uploader.Request")
def test_upload_uses_script_title_and_description(
    mock_request, mock_creds_class, mock_build, mock_media, monkeypatch
):
    monkeypatch.setenv("YOUTUBE_OAUTH_TOKEN", json.dumps({"refresh_token": "tok123"}))
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client_id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client_secret")

    mock_creds = MagicMock()
    mock_creds.expired = False
    mock_creds_class.return_value = mock_creds

    mock_youtube = MagicMock()
    mock_build.return_value = mock_youtube
    mock_insert_request = MagicMock()
    mock_youtube.videos.return_value.insert.return_value = mock_insert_request
    mock_insert_request.next_chunk.return_value = (None, {"id": "xyz"})

    from modules.youtube_uploader import YouTubeUploader
    uploader = YouTubeUploader()
    uploader.upload("/tmp/final.mp4", SCRIPT_RESULT)

    call_kwargs = mock_youtube.videos.return_value.insert.call_args.kwargs
    snippet = call_kwargs["body"]["snippet"]
    assert snippet["title"] == "The Last Signal"
    assert snippet["description"] == "A haunting journey through deep space."
    assert snippet["tags"] == ["scifi", "space", "horror", "cinematic", "shortfilm"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/modules/test_youtube_uploader.py -v
```

Expected: `ModuleNotFoundError: No module named 'modules.youtube_uploader'`

- [ ] **Step 3: Implement `modules/youtube_uploader.py`**

```python
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import YOUTUBE_CATEGORY_ID, YOUTUBE_SCOPES


class YouTubeUploader:
    def __init__(self):
        token_data = json.loads(os.environ["YOUTUBE_OAUTH_TOKEN"])
        self.creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=YOUTUBE_SCOPES,
        )
        if self.creds.expired:
            self.creds.refresh(Request())
        self.youtube = build("youtube", "v3", credentials=self.creds)

    def upload(self, video_path: str, script_result: dict) -> str:
        body = {
            "snippet": {
                "title": script_result["title"],
                "description": script_result["description"],
                "tags": script_result["tags"],
                "categoryId": YOUTUBE_CATEGORY_ID,
            },
            "status": {"privacyStatus": "public"},
        }
        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
        request = self.youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
        return f"https://www.youtube.com/watch?v={response['id']}"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/modules/test_youtube_uploader.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add modules/youtube_uploader.py tests/modules/test_youtube_uploader.py
git commit -m "feat: youtube uploader — OAuth2 + resumable upload + URL return"
```

---

## Task 7: Orchestrator

**Files:**
- Create: `orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_orchestrator.py
import pytest
from unittest.mock import MagicMock, patch


SCRIPT_RESULT = {
    "narrative": "In the void...",
    "title": "The Ghost Signal",
    "description": "desc",
    "tags": ["scifi"],
    "shots": ["shot1", "shot2", "shot3"],
}


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_returns_done_with_url(
    MockReader, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    mock_reader.get_pending_row.return_value = {
        "row_index": 2,
        "title": "Test",
        "story_brief": "A ghost astronaut",
        "genre": "blend",
        "duration_sec": 75,
    }
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    MockAudio.return_value.mix.return_value = "/tmp/final.mp4"
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=abc"

    from orchestrator import run_pipeline
    result = run_pipeline()

    assert result["status"] == "done"
    assert result["youtube_url"] == "https://youtube.com/watch?v=abc"
    mock_reader.update_done.assert_called_once_with(2, "https://youtube.com/watch?v=abc")


@patch("orchestrator.GSheetReader")
def test_run_pipeline_returns_no_pending_when_sheet_empty(MockReader):
    MockReader.return_value.get_pending_row.return_value = None

    from orchestrator import run_pipeline
    result = run_pipeline()

    assert result["status"] == "no_pending_rows"


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_writes_error_on_script_failure(
    MockReader, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    mock_reader.get_pending_row.return_value = {
        "row_index": 2, "title": "T", "story_brief": "b", "genre": "sci-fi", "duration_sec": 75
    }
    MockScript.return_value.generate.side_effect = RuntimeError("Claude API down")

    from orchestrator import run_pipeline
    with pytest.raises(RuntimeError, match="Claude API down"):
        run_pipeline()

    mock_reader.update_error.assert_called_once_with(2, "Claude API down")


@patch("orchestrator.YouTubeUploader")
@patch("orchestrator.AudioMixer")
@patch("orchestrator.VideoProducer")
@patch("orchestrator.ScriptGenerator")
@patch("orchestrator.GSheetReader")
def test_run_pipeline_sets_status_generating_before_script(
    MockReader, MockScript, MockVideo, MockAudio, MockYouTube
):
    mock_reader = MockReader.return_value
    mock_reader.get_pending_row.return_value = {
        "row_index": 2, "title": "T", "story_brief": "b", "genre": "blend", "duration_sec": 75
    }
    MockScript.return_value.generate.return_value = SCRIPT_RESULT
    MockVideo.return_value.produce.return_value = "/tmp/stitched.mp4"
    MockAudio.return_value.mix.return_value = "/tmp/final.mp4"
    MockYouTube.return_value.upload.return_value = "https://youtube.com/watch?v=xyz"

    from orchestrator import run_pipeline
    run_pipeline()

    status_calls = [c.args for c in mock_reader.update_status.call_args_list]
    assert ("generating",) in [args[1:] for args in status_calls]
    assert ("uploading",) in [args[1:] for args in status_calls]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: `ModuleNotFoundError: No module named 'orchestrator'`

- [ ] **Step 3: Implement `orchestrator.py`**

```python
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: 4 passed

- [ ] **Step 5: Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator — pipeline coordination with error propagation to GSheet"
```

---

## Task 8: Cloud Run Entrypoint

**Files:**
- Create: `main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
import pytest
from unittest.mock import patch


@patch("main.run_pipeline")
def test_run_endpoint_returns_200_on_success(mock_pipeline):
    mock_pipeline.return_value = {"status": "done", "youtube_url": "https://youtube.com/watch?v=abc"}

    from main import app
    client = app.test_client()
    resp = client.post("/run")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "done"


@patch("main.run_pipeline")
def test_run_endpoint_returns_200_for_no_pending(mock_pipeline):
    mock_pipeline.return_value = {"status": "no_pending_rows"}

    from main import app
    client = app.test_client()
    resp = client.post("/run")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "no_pending_rows"


@patch("main.run_pipeline")
def test_run_endpoint_returns_500_on_exception(mock_pipeline):
    mock_pipeline.side_effect = RuntimeError("Kling API down")

    from main import app
    client = app.test_client()
    resp = client.post("/run")

    assert resp.status_code == 500
    assert "Kling API down" in resp.get_json()["error"]


def test_health_endpoint_returns_ok():
    from main import app
    client = app.test_client()
    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Implement `main.py`**

```python
import os
from flask import Flask, jsonify
from dotenv import load_dotenv
from orchestrator import run_pipeline

load_dotenv()

app = Flask(__name__)


@app.route("/run", methods=["POST"])
def run():
    try:
        result = run_pipeline()
        return jsonify(result), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: 4 passed

- [ ] **Step 5: Run the full suite one more time**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: flask entrypoint for Cloud Run with /run and /health endpoints"
```

---

## Task 9: Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "main.py"]
```

- [ ] **Step 2: Create `.dockerignore`**

```
.env
.env.*
__pycache__/
*.pyc
*.pyo
.pytest_cache/
tests/
docs/
.superpowers/
.git/
```

- [ ] **Step 3: Build the Docker image locally**

```bash
docker build -t cinematic-agent .
```

Expected: image builds without errors; ffmpeg installed in container

- [ ] **Step 4: Verify ffmpeg is available in the container**

```bash
docker run --rm cinematic-agent ffmpeg -version
```

Expected: ffmpeg version output (e.g. `ffmpeg version 6.x`)

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "feat: Dockerfile with ffmpeg for Cloud Run deployment"
```

---

## Task 10: GCP Deployment

**Files:**
- No new files — GCP CLI commands only

- [ ] **Step 1: Set GCP project and enable required APIs**

```bash
gcloud config set project YOUR_GCP_PROJECT_ID

gcloud services enable run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  containerregistry.googleapis.com
```

Expected: all APIs enabled

- [ ] **Step 2: Store secrets in GCP Secret Manager**

```bash
# Run once per secret — substitute your actual values

echo -n "YOUR_ANTHROPIC_API_KEY" | \
  gcloud secrets create ANTHROPIC_API_KEY --data-file=-

echo -n "YOUR_KLING_ACCESS_KEY_ID" | \
  gcloud secrets create KLING_ACCESS_KEY_ID --data-file=-

echo -n "YOUR_KLING_SECRET_KEY" | \
  gcloud secrets create KLING_SECRET_KEY --data-file=-

echo -n "YOUR_ELEVENLABS_API_KEY" | \
  gcloud secrets create ELEVENLABS_API_KEY --data-file=-

echo -n '{"type":"service_account",...}' | \
  gcloud secrets create GOOGLE_SHEETS_CREDENTIALS --data-file=-

echo -n "YOUR_SHEET_ID" | \
  gcloud secrets create GOOGLE_SHEET_ID --data-file=-

echo -n "YOUR_YOUTUBE_CLIENT_ID" | \
  gcloud secrets create YOUTUBE_CLIENT_ID --data-file=-

echo -n "YOUR_YOUTUBE_CLIENT_SECRET" | \
  gcloud secrets create YOUTUBE_CLIENT_SECRET --data-file=-

echo -n '{"refresh_token":"YOUR_REFRESH_TOKEN"}' | \
  gcloud secrets create YOUTUBE_OAUTH_TOKEN --data-file=-
```

- [ ] **Step 3: Build and push container to GCP Artifact Registry**

```bash
gcloud artifacts repositories create cinematic-agent \
  --repository-format=docker \
  --location=us-central1

gcloud builds submit --tag us-central1-docker.pkg.dev/YOUR_PROJECT/cinematic-agent/app .
```

Expected: build succeeds and image is pushed

- [ ] **Step 4: Deploy to Cloud Run**

```bash
gcloud run deploy cinematic-agent \
  --image us-central1-docker.pkg.dev/YOUR_PROJECT/cinematic-agent/app \
  --region us-central1 \
  --no-allow-unauthenticated \
  --set-secrets \
    ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,\
    KLING_ACCESS_KEY_ID=KLING_ACCESS_KEY_ID:latest,\
    KLING_SECRET_KEY=KLING_SECRET_KEY:latest,\
    ELEVENLABS_API_KEY=ELEVENLABS_API_KEY:latest,\
    GOOGLE_SHEETS_CREDENTIALS=GOOGLE_SHEETS_CREDENTIALS:latest,\
    GOOGLE_SHEET_ID=GOOGLE_SHEET_ID:latest,\
    YOUTUBE_CLIENT_ID=YOUTUBE_CLIENT_ID:latest,\
    YOUTUBE_CLIENT_SECRET=YOUTUBE_CLIENT_SECRET:latest,\
    YOUTUBE_OAUTH_TOKEN=YOUTUBE_OAUTH_TOKEN:latest \
  --timeout=3600 \
  --memory=2Gi
```

Note: `--timeout=3600` (1 hour) is needed — generating 7 Kling shots takes ~30-60 min.

Expected: service deployed. Note the service URL from the output.

- [ ] **Step 5: Create Cloud Scheduler job (10:00 PM UTC+8 = 14:00 UTC)**

```bash
# Get the Cloud Run service URL first
SERVICE_URL=$(gcloud run services describe cinematic-agent \
  --region=us-central1 \
  --format='value(status.url)')

# Create service account for scheduler to invoke Cloud Run
gcloud iam service-accounts create scheduler-invoker \
  --display-name="Cloud Scheduler Invoker"

gcloud run services add-iam-policy-binding cinematic-agent \
  --region=us-central1 \
  --member="serviceAccount:scheduler-invoker@YOUR_PROJECT.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# Create the scheduler job
gcloud scheduler jobs create http cinematic-agent-daily \
  --location=us-central1 \
  --schedule="0 14 * * *" \
  --time-zone="UTC" \
  --uri="${SERVICE_URL}/run" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@YOUR_PROJECT.iam.gserviceaccount.com"
```

Expected: scheduler job created; will fire daily at 14:00 UTC (10:00 PM UTC+8)

- [ ] **Step 6: Test manually by triggering the scheduler**

```bash
gcloud scheduler jobs run cinematic-agent-daily --location=us-central1
```

Then watch logs:

```bash
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=cinematic-agent" \
  --limit=50 --format="value(textPayload)"
```

Expected: logs show pipeline stages completing, GSheet updated with `status=done` and YouTube URL

---

## Task 11: Discovery Mode

**Files:**
- Create: `discovery.py`

- [ ] **Step 1: Implement `discovery.py`**

This is a manual script (not part of the automated pipeline). Run it when you want to re-evaluate which AI video tool to use.

```python
"""
discovery.py — Run manually to evaluate and auto-select the best free AI video tool.
Usage: python discovery.py
Updates config.py with the winning tool.
"""
import os
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

RUBRIC = """
Evaluate each AI video generation tool against these criteria (score 0-5 each):
1. Free tier availability (5 = generous free credits daily)
2. API access (5 = full REST API, 0 = web-only)
3. Cinematic quality (5 = photorealistic, cinematic camera movement)
4. Story/narrative support (5 = long prompts, scene control)
5. Reliability and uptime

Tools to evaluate (as of 2026):
- Kling AI (klingai.com)
- HailuoAI / MiniMax (hailuoai.com)
- Runway Gen-4 (runwayml.com)
- Luma Dream Machine (lumalabs.ai)
- Pika Labs (pika.art)

Return a JSON array:
[{"name": "...", "scores": {...}, "total": N, "api_base_url": "...", "free_tier_notes": "..."}]
Sorted by total descending. Return JSON only.
"""

SYSTEM = "You are an expert in AI video generation tools. Provide accurate, up-to-date evaluations."


def discover_best_tool() -> dict:
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": RUBRIC}],
    )
    import json
    tools = json.loads(message.content[0].text.strip())
    winner = tools[0]
    print(f"\n=== Discovery Results ===")
    for t in tools:
        print(f"  {t['name']:25s} total={t['total']}/25  free={t['free_tier_notes']}")
    print(f"\n✓ Winner: {winner['name']} (score: {winner['total']}/25)")
    return winner


if __name__ == "__main__":
    winner = discover_best_tool()
    print(f"\nTo update config.py, set VIDEO_TOOL = '{winner['name'].lower().replace(' ', '_')}'")
    print(f"API base URL: {winner.get('api_base_url', 'check their developer docs')}")
```

- [ ] **Step 2: Run discovery manually to verify**

```bash
python discovery.py
```

Expected: printed ranked table of AI video tools; Kling AI or equivalent at top

- [ ] **Step 3: Commit**

```bash
git add discovery.py
git commit -m "feat: discovery mode — Claude evaluates and ranks free AI video tools"
```

---

## Task 12: YouTube OAuth2 Setup (One-Time)

**Files:**
- Create: `scripts/get_youtube_token.py` (run once locally, then delete)

- [ ] **Step 1: Create `scripts/get_youtube_token.py`**

```python
"""
Run this ONCE locally to get your YouTube OAuth2 refresh token.
Prerequisites:
1. Create a project at console.cloud.google.com
2. Enable YouTube Data API v3
3. Create OAuth2 credentials (Desktop app type)
4. Download client_secret.json to this directory
Usage: python scripts/get_youtube_token.py
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

token_data = {
    "token": creds.token,
    "refresh_token": creds.refresh_token,
}
print("\nStore this JSON as your YOUTUBE_OAUTH_TOKEN secret:")
print(json.dumps(token_data, indent=2))
```

- [ ] **Step 2: Run the script (requires browser)**

```bash
python scripts/get_youtube_token.py
```

A browser window opens. Log in with your YouTube account and grant access.
Copy the printed JSON → store it in GCP Secret Manager as `YOUTUBE_OAUTH_TOKEN`.

- [ ] **Step 3: Delete the script (contains no secrets but no longer needed)**

```bash
rm scripts/get_youtube_token.py client_secret.json
git add -A
git commit -m "chore: remove one-time OAuth2 token helper script"
```

---

## Final Verification

- [ ] **Run the full test suite**

```bash
pytest -v
```

Expected: all tests pass (no failures, no errors)

- [ ] **Trigger a manual end-to-end run via Cloud Scheduler**

```bash
gcloud scheduler jobs run cinematic-agent-daily --location=us-central1
```

Check GSheet: the first `pending` row should move through `generating → uploading → done` with a YouTube URL populated.

- [ ] **Verify the YouTube upload**

Open the YouTube URL from the GSheet. Confirm:
- Video plays with cinematic visuals (60–90 sec)
- Voiceover narration is present
- Background music is present
- Title and description match the genre
