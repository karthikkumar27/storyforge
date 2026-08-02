# tests/modules/test_preset.py
import pytest

from config import PRESETS
from modules.preset import Preset, active_preset, from_raw

MINIMAL = {
    "name": "Test Preset",
    "genres": ["sci-fi", "space"],
    "brief_system": "write a story",
    "video_style": "anime",
    "story_mode": "series",
    "series_parts": 3,
    "youtube_category": "24",
}


def test_a_preset_needs_only_the_core_fields():
    preset = from_raw("preset-x", MINIMAL)

    assert preset.key == "preset-x"
    assert preset.genres == ("sci-fi", "space")
    assert preset.extra_skills == ()
    assert preset.serialized_canon is False
    assert preset.tracks_episode_numbers is False
    assert preset.youtube_title_template is None


def test_a_preset_is_immutable():
    """Presets are read at import and shared; nothing should be able to mutate
    the active configuration at runtime."""
    preset = from_raw("preset-x", MINIMAL)

    with pytest.raises(Exception):
        preset.genres = ("horror",)


def test_genres_and_music_tags_become_tuples():
    preset = from_raw("preset-x", dict(MINIMAL, music_tags=["epic", "dark"]))

    assert isinstance(preset.genres, tuple)
    assert preset.music_tags == ("epic", "dark")


# -- capabilities -------------------------------------------------------------

def test_single_shot_native_is_read_from_pipeline_mode():
    assert from_raw("p", MINIMAL).is_single_shot_native is False
    assert from_raw(
        "p", dict(MINIMAL, pipeline_mode="single_shot_native")
    ).is_single_shot_native is True


def test_card_durations_default_to_zero_when_unconfigured():
    preset = from_raw("p", MINIMAL)

    assert preset.title_card_duration == 0.0
    assert preset.end_card_duration == 0.0


def test_card_durations_come_from_the_card_config():
    preset = from_raw("p", dict(
        MINIMAL,
        title_card={"image": "a.png", "duration": 2.0},
        end_card={"image": "b.png", "duration": 5.0},
    ))

    assert preset.title_card_duration == 2.0
    assert preset.end_card_duration == 5.0


# -- ending style -------------------------------------------------------------

def test_presets_close_their_stories_by_default():
    preset = from_raw("p", MINIMAL)

    assert preset.ending_style == "complete"
    assert "MUST feel COMPLETE" in preset.narrative_closure_rule
    assert "No unfinished sentences" in preset.narrative_closure_rule


def test_an_open_ending_preset_forbids_resolving_the_confrontation():
    preset = from_raw("p", dict(MINIMAL, ending_style="open"))

    rule = preset.narrative_closure_rule
    assert "MUST NOT RESOLVE" in rule
    assert "Do NOT show who wins" in rule
    assert "to be continued" in rule          # explicitly banned as text
    assert "MUST feel COMPLETE within this video" not in rule


def test_an_unknown_ending_style_falls_back_to_closing_the_story():
    """A typo in config must not silently produce open-ended episodes."""
    preset = from_raw("p", dict(MINIMAL, ending_style="opne"))

    assert "MUST feel COMPLETE" in preset.narrative_closure_rule


def test_only_the_action_preset_leaves_its_ending_open():
    open_ended = [
        key for key, raw in PRESETS.items()
        if from_raw(key, raw).ending_style == "open"
    ]

    assert open_ended == ["preset-9"]


# -- published title ----------------------------------------------------------

def test_no_template_means_no_numbered_title():
    """The caller then falls back to its Series/Part formatting."""
    assert from_raw("p", MINIMAL).format_youtube_title("The Blue Dot", 6) is None


def test_the_template_fills_in_episode_number_and_title():
    preset = from_raw("p", dict(
        MINIMAL,
        youtube_title_template="The Chronicle of Zenith — Ep {episode_number}: {title}",
    ))

    assert preset.format_youtube_title("The Blue Dot", 6) == (
        "The Chronicle of Zenith — Ep 6: The Blue Dot"
    )


@pytest.mark.parametrize("episode_number", [None, "", 0])
def test_without_an_episode_number_there_is_no_numbered_title(episode_number):
    preset = from_raw("p", dict(
        MINIMAL, youtube_title_template="Ep {episode_number}: {title}",
    ))

    assert preset.format_youtube_title("The Blue Dot", episode_number) is None


# -- the real presets ---------------------------------------------------------

def test_every_configured_preset_builds():
    """A malformed preset block should fail here, not three modules deep."""
    for key, raw in PRESETS.items():
        preset = from_raw(key, raw)
        assert preset.key == key
        assert preset.genres, f"{key} has no genres"


def test_zenith_declares_the_capabilities_that_used_to_be_string_checks():
    zenith = from_raw("preset-7", PRESETS["preset-7"])

    assert zenith.serialized_canon is True
    assert zenith.tracks_episode_numbers is True
    assert zenith.extra_skills == ("chronicle-of-zenith-canon",)
    assert zenith.episode_sheet_env == "ALAN_STORY_GOOGLE_SHEET_ID"
    assert zenith.format_youtube_title("The Blue Dot", 6) == (
        "The Chronicle of Zenith — Ep 6: The Blue Dot"
    )


@pytest.mark.parametrize("key", ["preset-4", "preset-5", "preset-6"])
def test_kids_presets_load_the_kids_skill_and_declare_their_audience(key):
    preset = from_raw(key, PRESETS[key])

    assert preset.extra_skills == ("kids-content-specialist",)
    assert preset.made_for_kids is True


@pytest.mark.parametrize("key", ["preset-1", "preset-2", "preset-3", "preset-8", "preset-9"])
def test_other_presets_claim_no_serialized_canon(key):
    preset = from_raw(key, PRESETS[key])

    assert preset.serialized_canon is False
    assert preset.tracks_episode_numbers is False
    assert preset.youtube_title_template is None


def test_only_zenith_uses_a_dedicated_episode_sheet():
    with_sheet = [
        key for key, raw in PRESETS.items()
        if from_raw(key, raw).episode_sheet_env
    ]

    assert with_sheet == ["preset-7"]


def test_the_shonen_action_preset_is_configured_for_unique_standalone_fights():
    shonen = from_raw("preset-9", PRESETS["preset-9"])

    # Unique stories every time -> standalone, never a continuing series
    assert shonen.story_mode == "standalone"
    assert shonen.series_parts == 1
    # The fight is cut at its peak
    assert shonen.ending_style == "open"
    # Character stays consistent across the shots of one fight
    assert shonen.per_shot_storyboards is True
    # No preset-specific skill: the common craft stack + the YouTube optimiser
    # already cover it
    assert shonen.extra_skills == ()
    assert len(shonen.genres) == 6


def test_active_preset_follows_the_environment(monkeypatch):
    import config
    monkeypatch.setattr(config, "ACTIVE_PRESET", "preset-7")

    assert active_preset().key == "preset-7"
    assert active_preset().serialized_canon is True


def test_chaining_is_off_unless_a_preset_asks_for_it():
    from modules.preset import from_raw
    from config import PRESETS

    for key, raw in PRESETS.items():
        if key == "preset-9":
            continue
        assert from_raw(key, raw).chain_reference_frames is False, key


def test_preset_9_chains_reference_frames():
    from modules.preset import from_raw
    from config import PRESETS

    assert from_raw("preset-9", PRESETS["preset-9"]).chain_reference_frames is True


def test_preset_7_still_uses_batch_storyboards_not_chaining():
    """preset-7 is a 200-episode series with locked canon — it does not get
    this until a real before/after proves the two-base call holds fidelity."""
    from modules.preset import from_raw
    from config import PRESETS

    preset = from_raw("preset-7", PRESETS["preset-7"])
    assert preset.per_shot_storyboards is True
    assert preset.chain_reference_frames is False
