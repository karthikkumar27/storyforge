"""The active Preset, as a value rather than twenty module globals.

A Preset is a named content configuration: which genres, which voice, which
visual style, which series rules — and, crucially, which *capabilities* the
pipeline should switch on.

Capabilities replace scattered identity checks. Code used to ask
`ACTIVE_PRESET == "preset-7"` in eleven places across seven files, which meant
adding a new preset required hunting all of them. It now asks what it actually
needs to know:

    preset.serialized_canon        arc context, locked roster, character form
    preset.tracks_episode_numbers  absolute Episode Numbers across a Series
    preset.extra_skills            preset-specific skills to load
    preset.youtube_title_template  how to format the published title

Each is data in config.PRESETS, so a new preset is a config block, not a code
change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Preset:
    key: str
    name: str
    genres: tuple[str, ...]
    brief_system: str
    video_style: str
    story_mode: str
    series_parts: int
    youtube_category: str
    voice_map: dict = field(default_factory=dict)
    music_tags: tuple[str, ...] = ()

    # -- capabilities ---------------------------------------------------------
    extra_skills: tuple[str, ...] = ()
    serialized_canon: bool = False
    tracks_episode_numbers: bool = False
    youtube_title_template: str | None = None
    episode_sheet_env: str | None = None
    # "complete" — the story resolves inside the episode (the default, and what
    # every preset did before this existed).
    # "open"     — setup and stakes are complete, but the confrontation is left
    #              unresolved on purpose.
    ending_style: str = "complete"

    # -- optional feature configuration --------------------------------------
    per_shot_storyboards: bool = False
    made_for_kids: bool = False
    youtube_hashtags: tuple[str, ...] = ()
    default_ref_image: str | None = None
    image_model: str | None = None
    pipeline_mode: str | None = None
    title_card: dict | None = None
    end_card: dict | None = None
    audio_mix: dict | None = None
    seedance2: dict | None = None

    # -- derived questions callers actually ask -------------------------------

    @property
    def is_single_shot_native(self) -> bool:
        """True when one model call produces the whole video, so there is no
        script, no per-shot storyboards, no stitching and no audio mixing."""
        return self.pipeline_mode == "single_shot_native"

    @property
    def narrative_closure_rule(self) -> str:
        """The closure instruction handed to the script generator.

        Lives here rather than hardcoded in the prompt because presets disagree:
        most want a story that lands, an action preset wants the fight cut at its
        peak. The wording is deliberately forceful — this sits inside the JSON
        schema description, which the model weights heavily, so a soft hint
        loses to the surrounding template.
        """
        if self.ending_style == "open":
            return (
                "The SETUP and STAKES must feel complete, but the CONFRONTATION "
                "MUST NOT RESOLVE. End at the peak — mid-strike, mid-reveal, on "
                "the turn. Do NOT show who wins. Do NOT resolve the fight. Do NOT "
                "write an epilogue. The final line must leave the outcome hanging "
                "while still feeling deliberate rather than truncated. Never write "
                "'to be continued' — the final image and final line do that work."
            )
        return (
            "The story MUST feel COMPLETE within this video — beginning, middle, "
            "and end. No unfinished sentences, no trailing cliffhangers, no "
            "'to be continued' feel. The viewer should feel satisfied at the end."
        )

    @property
    def title_card_duration(self) -> float:
        return float((self.title_card or {}).get("duration", 0.0))

    @property
    def end_card_duration(self) -> float:
        return float((self.end_card or {}).get("duration", 0.0))

    def format_youtube_title(self, title: str, episode_number: Any = None) -> str | None:
        """Apply this preset's published-title format.

        Returns None when the preset has no template, or when the Episode has no
        Episode Number to put in it — the caller then falls back to its
        Series/Part formatting.
        """
        if not self.youtube_title_template or not episode_number:
            return None
        return self.youtube_title_template.format(
            title=title, episode_number=episode_number
        )


def from_raw(key: str, raw: dict) -> Preset:
    """Build a Preset from one entry of config.PRESETS."""
    return Preset(
        key=key,
        name=raw["name"],
        genres=tuple(raw["genres"]),
        brief_system=raw["brief_system"],
        video_style=raw["video_style"],
        story_mode=raw["story_mode"],
        series_parts=raw["series_parts"],
        youtube_category=raw["youtube_category"],
        voice_map=raw.get("voice_map") or {},
        music_tags=tuple(raw.get("music_tags") or ()),
        extra_skills=tuple(raw.get("extra_skills") or ()),
        serialized_canon=bool(raw.get("serialized_canon", False)),
        tracks_episode_numbers=bool(raw.get("tracks_episode_numbers", False)),
        youtube_title_template=raw.get("youtube_title_template"),
        episode_sheet_env=raw.get("episode_sheet_env"),
        ending_style=raw.get("ending_style", "complete"),
        per_shot_storyboards=bool(raw.get("per_shot_storyboards", False)),
        made_for_kids=bool(raw.get("made_for_kids", False)),
        youtube_hashtags=tuple(raw.get("youtube_hashtags") or ()),
        default_ref_image=raw.get("default_ref_image"),
        image_model=raw.get("image_model"),
        pipeline_mode=raw.get("pipeline_mode"),
        title_card=raw.get("title_card"),
        end_card=raw.get("end_card"),
        audio_mix=raw.get("audio_mix"),
        seedance2=raw.get("seedance2"),
    )


def active_preset() -> Preset:
    """The Preset selected by CONTENT_PRESET."""
    from config import ACTIVE_PRESET, PRESETS
    return from_raw(ACTIVE_PRESET, PRESETS[ACTIVE_PRESET])
