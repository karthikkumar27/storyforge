# tests/modules/test_storyboard.py
import pytest

from modules.storyboard import (
    CHARACTER_ABSENT_MARKERS,
    ChainedStoryboards,
    build_continuity_prompt,
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


class ListEditor:
    """StubEditor's sibling: accepts a list-or-string base, records both."""

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
        return f"https://cdn/chained{len(self.calls)}.png"


@pytest.fixture(autouse=True)
def no_aspect_fetch(monkeypatch):
    """frame_for always runs its return value through portrait_anchor, which
    -- unpatched -- fetches the URL over real HTTP to measure it. Most tests
    below don't care about aspect correction, so default it to identity and
    keep this whole module network-free. `portrait_anchor` is only ever
    reached by ChainedStoryboards.frame_for, so this has no effect on the
    build_storyboards tests above.

    test_the_result_is_aspect_checked_before_it_is_returned re-patches the
    same target with its own monkeypatch call, which simply wins -- so it
    still exercises the real call path this fixture stands in for.
    """
    monkeypatch.setattr(
        "modules.storyboard.portrait_anchor",
        lambda url, **kw: url,
    )


# -- the continuity prompt ----------------------------------------------------

def test_continuity_prompt_names_which_base_owns_identity():
    """Probing showed text wins over images when they conflict, so the
    instruction has to be explicit about precedence."""
    prompt = build_continuity_prompt("Kenji lunges forward", "anime cel-shaded")

    assert "first image" in prompt.lower()
    assert "second image" in prompt.lower()
    assert "Scene: Kenji lunges forward" in prompt


def test_continuity_prompt_still_asks_for_a_vertical_first_frame():
    prompt = build_continuity_prompt("Kenji lunges forward", "anime")

    assert "9:16" in prompt
    assert "START of the action" in prompt
    assert "no motion blur" in prompt


# -- the supplier -------------------------------------------------------------

def test_first_shot_uses_the_reference_alone():
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    supplier.frame_for(0, "the bridge at night", None)

    base, _ = editor.calls[0]
    assert base == "https://cdn/ref.png"


def test_later_shots_pass_reference_first_and_previous_frame_second(monkeypatch, tmp_path):
    clip = tmp_path / "shot_00.mp4"
    clip.write_bytes(b"fake")
    monkeypatch.setattr(
        "modules.storyboard.extract_last_frame", lambda path, **kw: str(clip)
    )
    monkeypatch.setattr(
        "modules.storyboard.to_data_uri", lambda path, **kw: "data:image/png;base64,ZZZ"
    )
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    supplier.frame_for(1, "Kenji lunges", str(clip))

    base, _ = editor.calls[0]
    assert base == ["https://cdn/ref.png", "data:image/png;base64,ZZZ"]


def test_extraction_failure_falls_back_to_the_reference_alone(monkeypatch, tmp_path):
    """One shot loses continuity; the episode continues."""
    from modules.frame_chain import FrameExtractionError
    clip = tmp_path / "shot_00.mp4"
    clip.write_bytes(b"fake")

    def boom(path, **kw):
        raise FrameExtractionError("corrupt clip")

    monkeypatch.setattr("modules.storyboard.extract_last_frame", boom)
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    result = supplier.frame_for(1, "Kenji lunges", str(clip))

    assert editor.calls[0][0] == "https://cdn/ref.png"
    assert "two images" not in editor.calls[0][1]
    assert result is not None


def test_an_edit_failure_returns_none_rather_than_raising():
    """None tells the video producer to fall back to the shared reference."""
    editor = ListEditor([RuntimeError("content filter")])
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    assert supplier.frame_for(0, "the bridge", None) is None


def test_character_absent_shots_still_use_the_style_only_prompt():
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    supplier.frame_for(0, "POV shot — the altar cracks", None)

    _, prompt = editor.calls[0]
    assert "STYLE anchor only" in prompt


def test_the_result_is_aspect_checked_before_it_is_returned(monkeypatch):
    """A two-image edit silently returns landscape. Every storyboard goes
    through portrait_anchor before it can become a first frame."""
    seen = []
    monkeypatch.setattr(
        "modules.storyboard.portrait_anchor",
        lambda url, **kw: seen.append(url) or "data:image/png;base64,CROPPED",
    )
    editor = ListEditor(["https://cdn/wide.png"])
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", generator=editor, log=lambda _: None,
    )

    result = supplier.frame_for(0, "the bridge", None)

    assert seen == ["https://cdn/wide.png"]
    assert result == "data:image/png;base64,CROPPED"


# -- appearance injection -----------------------------------------------------

APPEARANCE = (
    "A teenage Japanese girl, short black hair pushed back with a worn yellow "
    "sweatband, oversized orange maintenance jumpsuit unzipped to the waist over "
    "a white fitted shirt, black rubber work gloves, beat-up steel-toed boots."
)


def test_appearance_absent_leaves_the_present_prompt_byte_identical():
    """The regression guard for all five storyboard presets."""
    assert build_edit_prompt("Alan turns from the console", "anime") == (
        "Use the reference image as the base — preserve the main character's face, "
        "hair, outfit, and anime style exactly. Render this scene as a 9:16 "
        "vertical still frame at the START of the action, no motion blur. If the shot "
        "prompt explicitly names other characters or entities (a holographic AI "
        "manifesting as light, another person, a creature), include them rendered "
        "exactly as the shot prompt describes. Scene: Alan turns from the console"
    )


def test_appearance_absent_leaves_the_continuity_prompt_byte_identical():
    """The regression guard for all five storyboard presets."""
    expected = (
        "You are given two images. The FIRST image is the authority on WHO the "
        "character is — preserve their face, hair, eye colour, outfit and the anime "
        "style from it exactly. The SECOND image is the final moment of the previous "
        "shot — use it for continuity of lighting, weather, wardrobe state and where "
        "other characters are standing, and keep any second character looking exactly "
        "as they do there. Where the two images disagree about the main character's "
        "appearance, the FIRST image wins. Render this scene as a 9:16 vertical still "
        "frame at the START of the action, no motion blur. Scene: Kenji lunges forward"
    )
    assert build_continuity_prompt("Kenji lunges forward", "anime") == expected
    assert build_continuity_prompt("Kenji lunges forward", "anime", None) == expected
    assert "always looks exactly like this" not in expected


def test_appearance_is_pasted_verbatim_into_the_edit_prompt():
    prompt = build_edit_prompt("Sora wades forward", "anime", APPEARANCE)

    assert APPEARANCE in prompt
    assert "Scene: Sora wades forward" in prompt


def test_appearance_is_pasted_verbatim_into_the_continuity_prompt():
    prompt = build_continuity_prompt("Sora wades forward", "anime", APPEARANCE)

    assert APPEARANCE in prompt
    assert "two images" in prompt          # the continuity wording survives
    assert "Scene: Sora wades forward" in prompt


def test_the_appearance_block_comes_before_the_scene():
    """The defect is that scene language out-weighs the character. The remedy
    depends on the character text being early and marked as overriding."""
    prompt = build_edit_prompt("Sora wades forward", "anime", APPEARANCE)

    assert prompt.index(APPEARANCE) < prompt.index("Scene:")
    assert prompt.index(APPEARANCE) < prompt.index("Use the reference image")


def test_the_appearance_block_comes_before_the_scene_in_the_continuity_prompt():
    """Same mechanism as the edit prompt: placement is what makes the override
    work, so the continuity builder needs it too, not just the edit builder."""
    prompt = build_continuity_prompt("Sora wades forward", "anime", APPEARANCE)

    assert prompt.index(APPEARANCE) < prompt.index("Scene:")
    assert prompt.index(APPEARANCE) < prompt.index("You are given two images")


def test_the_appearance_block_asserts_authority_over_the_scene():
    prompt = build_edit_prompt("Sora wades forward", "anime", APPEARANCE)
    lowered = prompt.lower()

    assert "authority" in lowered
    assert "does not change how the character looks" in lowered


def test_the_appearance_block_asserts_authority_over_the_scene_in_the_continuity_prompt():
    prompt = build_continuity_prompt("Sora wades forward", "anime", APPEARANCE)
    lowered = prompt.lower()

    assert "authority" in lowered
    assert "does not change how the character looks" in lowered


def test_a_character_absent_shot_never_gets_the_appearance():
    """POV and wide-exterior shots deliberately have no character in frame.
    Describing one there is noise, and may coax the model into drawing them."""
    for builder in (build_edit_prompt, build_continuity_prompt):
        prompt = builder("POV shot — the altar cracks", "anime", APPEARANCE)
        assert APPEARANCE not in prompt
        assert "STYLE anchor only" in prompt or "STYLE anchor" in prompt


def test_an_empty_appearance_is_treated_as_absent():
    for value in ("", "   "):
        assert build_edit_prompt("Sora wades", "anime", value) == build_edit_prompt(
            "Sora wades", "anime"
        )


def test_an_empty_appearance_is_treated_as_absent_in_the_continuity_prompt():
    for value in ("", "   "):
        assert build_continuity_prompt(
            "Sora wades", "anime", value
        ) == build_continuity_prompt("Sora wades", "anime")
