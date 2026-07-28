# tests/modules/test_storyboard.py
import pytest

from modules.storyboard import (
    CHARACTER_ABSENT_MARKERS,
    build_edit_prompt,
    build_storyboards,
    character_is_absent,
)


class StubEditor:
    """Records the prompts it was given; replays scripted results."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.calls = []

    def edit_image(self, base_image_url, prompt):
        self.calls.append((base_image_url, prompt))
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return f"https://cdn/sb{len(self.calls)}.png"


# -- mode detection -----------------------------------------------------------

@pytest.mark.parametrize("shot", [
    "POV shot — the character's hand reaches toward the cracked altar",
    "Extreme wide of the valley, the ship growing smaller behind",
    "The camera pushes through the doorway into amber light",
    "Exterior — from outside the ship, hull plating streaked with frost",
    "EWS, the ridge line at dawn",
])
def test_shots_that_hide_the_character_are_detected(shot):
    assert character_is_absent(shot) is True


@pytest.mark.parametrize("shot", [
    "Alan turns from the console, jaw tight, dust drifting past",
    "Close on Veth-Ka's light rippling as it speaks",
    "Tracking shot — she walks the length of the corridor",
])
def test_ordinary_shots_keep_the_character(shot):
    assert character_is_absent(shot) is False


def test_detection_ignores_case():
    assert character_is_absent("pov SHOT of the artifact") is True


def test_every_marker_actually_triggers_detection():
    """Guards against a marker being added with stray casing or whitespace that
    can never match the lowercased shot text."""
    for marker in CHARACTER_ABSENT_MARKERS:
        assert character_is_absent(f"Something {marker} something") is True


# -- prompt building ----------------------------------------------------------

def test_character_present_prompt_locks_face_hair_and_outfit():
    prompt = build_edit_prompt("Alan turns from the console", "anime cel-shaded")

    assert "preserve the main character's face" in prompt
    assert "hair, outfit, and anime cel-shaded style exactly" in prompt
    assert "Scene: Alan turns from the console" in prompt


def test_character_absent_prompt_uses_the_reference_as_style_only():
    prompt = build_edit_prompt("POV shot — the altar cracks", "anime cel-shaded")

    assert "STYLE anchor only" in prompt
    assert "should NOT be in frame" in prompt
    assert "preserve the main character's face" not in prompt


def test_the_style_is_interpolated_not_hardcoded():
    """The two old copies had drifted: one interpolated the preset's video
    style, the other hardcoded the word "illustration"."""
    for shot in ("Alan turns", "POV shot of the altar"):
        prompt = build_edit_prompt(shot, "colorful 3D animated cartoon")
        assert "colorful 3D animated cartoon" in prompt


def test_both_modes_ask_for_a_vertical_first_frame():
    for shot in ("Alan turns", "POV shot of the altar"):
        prompt = build_edit_prompt(shot, "anime")
        assert "9:16" in prompt
        assert "START of the action" in prompt
        assert "no motion blur" in prompt


# -- the batch ----------------------------------------------------------------

def test_one_storyboard_per_shot_in_order():
    editor = StubEditor(["https://cdn/a.png", "https://cdn/b.png", "https://cdn/c.png"])

    result = build_storyboards(
        ["shot one", "shot two", "shot three"],
        "https://cdn/alan.png",
        style="anime",
        generator=editor,
        log=lambda _: None,
    )

    assert result == ["https://cdn/a.png", "https://cdn/b.png", "https://cdn/c.png"]


def test_every_shot_is_anchored_to_the_same_reference_image():
    editor = StubEditor()

    build_storyboards(
        ["one", "two"], "https://cdn/alan.png",
        style="anime", generator=editor, log=lambda _: None,
    )

    assert [base for base, _ in editor.calls] == [
        "https://cdn/alan.png", "https://cdn/alan.png",
    ]


def test_a_failed_shot_becomes_none_and_the_rest_continue():
    """None tells the video producer to fall back to the shared reference for
    that shot -- one failure costs pose variety, not the episode."""
    editor = StubEditor([
        "https://cdn/a.png",
        RuntimeError("content filter"),
        "https://cdn/c.png",
    ])

    result = build_storyboards(
        ["one", "two", "three"], "https://cdn/alan.png",
        style="anime", generator=editor, log=lambda _: None,
    )

    assert result == ["https://cdn/a.png", None, "https://cdn/c.png"]


def test_every_shot_is_attempted_even_after_a_failure():
    editor = StubEditor([RuntimeError("boom"), RuntimeError("boom"), "https://cdn/c.png"])

    build_storyboards(
        ["one", "two", "three"], "https://cdn/alan.png",
        style="anime", generator=editor, log=lambda _: None,
    )

    assert len(editor.calls) == 3


def test_no_shots_means_no_calls():
    editor = StubEditor()

    assert build_storyboards(
        [], "https://cdn/alan.png", style="anime", generator=editor, log=lambda _: None,
    ) == []
    assert editor.calls == []


def test_mixed_shots_get_the_prompt_mode_they_need():
    editor = StubEditor()

    build_storyboards(
        ["Alan turns from the console", "POV shot — the altar cracks"],
        "https://cdn/alan.png",
        style="anime", generator=editor, log=lambda _: None,
    )

    present_prompt, absent_prompt = (prompt for _, prompt in editor.calls)
    assert "preserve the main character's face" in present_prompt
    assert "STYLE anchor only" in absent_prompt


def test_progress_is_reported_per_shot():
    lines = []

    build_storyboards(
        ["one", "two"], "https://cdn/alan.png",
        style="anime", generator=StubEditor(), log=lines.append,
    )

    assert any("shot 1/2" in line for line in lines)
    assert any("shot 2/2" in line for line in lines)
