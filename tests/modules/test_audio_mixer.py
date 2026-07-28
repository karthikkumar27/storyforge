# tests/modules/test_audio_mixer.py
#
# The ElevenLabs transport and the ffmpeg runner are injected, so these tests
# need no API key, no network and no ffmpeg binary.
import pytest

from config import VOICE_MAP
from modules.audio_mixer import AudioMixer

# Some presets (e.g. preset-8) generate native audio and carry no voice map.
requires_voice_map = pytest.mark.skipif(
    not VOICE_MAP, reason="active preset has no voice_map (native-audio preset)"
)


class FakeResponse:
    def __init__(self, status_code=200, content=b"fake_audio_bytes", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text


class FakeHttp:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.responses:
            return self.responses.pop(0)
        return FakeResponse()


class FakeRunner:
    """Stands in for subprocess.run. Records ffmpeg/ffprobe invocations."""

    def __init__(self, stdout="12.0"):
        self.commands = []
        self.stdout = stdout

    def __call__(self, cmd, **kwargs):
        self.commands.append(cmd)

        class _Result:
            pass

        result = _Result()
        result.stdout = self.stdout
        result.returncode = 0
        return result

    def ffmpeg_commands(self):
        return [c for c in self.commands if c[0] == "ffmpeg"]


def _mixer(http=None, runner=None):
    return AudioMixer(api_key="el-key", http=http or FakeHttp(), run=runner or FakeRunner())


# -- voice selection ----------------------------------------------------------

@requires_voice_map
def test_voiceover_uses_the_voice_mapped_to_the_genre(tmp_path):
    http = FakeHttp()
    genre, expected_voice_id = next(iter(VOICE_MAP.items()))

    _mixer(http)._generate_voiceover("In the void...", genre, str(tmp_path))

    assert expected_voice_id in http.calls[0][0]


@requires_voice_map
def test_an_unknown_genre_falls_back_to_the_presets_first_voice(tmp_path):
    http = FakeHttp()

    _mixer(http)._generate_voiceover("Something dark...", "not-a-real-genre", str(tmp_path))

    assert list(VOICE_MAP.values())[0] in http.calls[0][0]


@requires_voice_map
def test_a_failed_tts_call_raises_with_the_status(tmp_path):
    http = FakeHttp([FakeResponse(status_code=401, text="bad key")])

    with pytest.raises(RuntimeError, match="401"):
        _mixer(http)._generate_voiceover("text", "sci-fi", str(tmp_path))


# -- construction -------------------------------------------------------------

def test_an_explicit_api_key_is_used_without_touching_the_environment(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    assert AudioMixer(api_key="explicit").api_key == "explicit"


def test_a_missing_api_key_still_fails_loudly(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        AudioMixer()


# -- mix() --------------------------------------------------------------------

def test_mix_passes_video_voiceover_and_bgm_to_ffmpeg(tmp_path, monkeypatch):
    runner = FakeRunner()
    mixer = _mixer(runner=runner)
    monkeypatch.setattr(mixer, "_generate_voiceover", lambda *a: str(tmp_path / "vo.mp3"))
    monkeypatch.setattr(mixer, "_generate_bgm", lambda *a: str(tmp_path / "bgm.mp3"))

    mixer.mix(str(tmp_path / "stitched.mp4"), "narrative", "sci-fi")

    cmd = runner.ffmpeg_commands()[0]
    assert str(tmp_path / "stitched.mp4") in cmd
    assert str(tmp_path / "vo.mp3") in cmd
    assert str(tmp_path / "bgm.mp3") in cmd
    assert "amix=inputs=2" in " ".join(cmd)


def test_mix_falls_back_to_voiceover_only_when_bgm_is_unavailable(tmp_path, monkeypatch):
    runner = FakeRunner()
    mixer = _mixer(runner=runner)
    monkeypatch.setattr(mixer, "_generate_voiceover", lambda *a: str(tmp_path / "vo.mp3"))
    monkeypatch.setattr(mixer, "_generate_bgm", lambda *a: None)

    mixer.mix(str(tmp_path / "stitched.mp4"), "narrative", "sci-fi")

    cmd = runner.ffmpeg_commands()[0]
    assert str(tmp_path / "vo.mp3") in cmd
    assert "-filter_complex" not in cmd


def test_mix_output_path_is_final_mp4(tmp_path, monkeypatch):
    mixer = _mixer()
    monkeypatch.setattr(mixer, "_generate_voiceover", lambda *a: str(tmp_path / "vo.mp3"))
    monkeypatch.setattr(mixer, "_generate_bgm", lambda *a: None)

    output = mixer.mix(str(tmp_path / "stitched.mp4"), "narrative", "sci-fi")

    assert output == str(tmp_path / "final.mp4")


def test_mix_refuses_a_path_it_cannot_derive_an_output_from(tmp_path):
    with pytest.raises(ValueError, match="stitched.mp4"):
        _mixer().mix(str(tmp_path / "wrong_name.mp4"), "narrative", "sci-fi")


# -- mix_with_native_audio() --------------------------------------------------

def _native_mix(tmp_path, monkeypatch, **kwargs):
    runner = FakeRunner(stdout="60.0")     # 60-second video
    mixer = _mixer(runner=runner)
    monkeypatch.setattr(mixer, "_generate_voiceover", lambda *a: str(tmp_path / "vo.mp3"))
    mixer.mix_with_native_audio(
        str(tmp_path / "stitched.mp4"), "narrative", "sci-fi", **kwargs
    )
    cmd = runner.ffmpeg_commands()[0]
    return " ".join(cmd[cmd.index("-filter_complex") + 1:cmd.index("-filter_complex") + 2])


def test_native_mix_layers_narration_over_the_ambient_bed(tmp_path, monkeypatch):
    graph = _native_mix(tmp_path, monkeypatch, narration_volume=1.0, ambient_volume=0.32)

    assert "volume=1.0" in graph          # narration
    assert "volume=0.32" in graph         # native ambient, ducked
    assert "amix=inputs=2" in graph


def test_narration_is_delayed_past_the_title_card(tmp_path, monkeypatch):
    """preset-7 starts narration at 3.0s so Adam doesn't talk over the sting."""
    graph = _native_mix(tmp_path, monkeypatch, narration_start_offset=3.0)

    assert "adelay=3000|3000" in graph


def test_no_delay_filter_when_narration_starts_immediately(tmp_path, monkeypatch):
    graph = _native_mix(tmp_path, monkeypatch, narration_start_offset=0.0)

    assert "adelay" not in graph


def test_narration_fades_out_before_the_end_card(tmp_path, monkeypatch):
    # 60s video, 5s end card -> story window ends at 55s, fade starts at 54.5s
    graph = _native_mix(tmp_path, monkeypatch, narration_end_buffer=5.0)

    assert "afade=t=out:st=54.5:d=0.5" in graph


def test_no_fade_filter_without_an_end_card(tmp_path, monkeypatch):
    graph = _native_mix(tmp_path, monkeypatch, narration_end_buffer=0.0)

    assert "afade" not in graph


def test_probe_duration_reads_ffprobe_output(tmp_path):
    runner = FakeRunner(stdout="  11.97\n")

    assert _mixer(runner=runner)._probe_duration("x.mp4") == pytest.approx(11.97)
    assert runner.commands[0][0] == "ffprobe"
