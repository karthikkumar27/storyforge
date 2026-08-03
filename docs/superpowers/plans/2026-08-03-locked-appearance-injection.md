# Locked Appearance Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop storyboard edits discarding the character's costume, by describing the locked appearance in *words* — the same modality the scene is described in — instead of relying on the reference image's pixels alone.

**Architecture:** Both storyboard prompt builders gain an optional `appearance` parameter. When present, an authoritative character block is placed first, ahead of the scene. Both suppliers thread it through. The orchestrator sources it from the characters sheet for `serialized_canon` presets and from `character_image_prompt` for everything else. When absent, every prompt is byte-identical to today.

**Tech Stack:** Python 3.12, pytest. No new dependencies, no new API calls, no per-episode cost.

**Spec:** `docs/superpowers/specs/2026-08-03-locked-appearance-injection-design.md`

## Global Constraints

- **`appearance=None` must produce a byte-identical prompt to today.** This is the regression guard for all five affected presets (preset-1, 2, 3, 7, 9) and the fallback for any caller with no source. Assert it against the literal current strings, not a paraphrase.
- **Never inject appearance into a character-absent prompt.** `character_is_absent(shot_prompt)` is True for POV, extreme-wide and environmental shots where the character is deliberately out of frame. Describing the character there is noise at best and may coax the model into drawing them.
- **The appearance block goes FIRST**, ahead of the reference-image and style instructions. The defect being fixed is that scene language out-weighs character pixels; the remedy depends on character language being early and marked as overriding.
- **The appearance text is pasted verbatim.** Do not summarise, truncate, or reformat it — for preset-7 it is locked canon.
- **No config flag.** This is corrected behaviour for every preset with `per_shot_storyboards: True`, not an opt-in capability.
- **Nothing raises.** A missing or empty source yields today's prompt.
- **Tests run without network.** Inject stubs at constructor/parameter seams; never patch module internals except where a test explicitly targets a module-level name.
- Run the full suite with `python3 -m pytest tests -q` (currently 301 passed, 4 skipped).

---

### Task 1: The prompt builders accept an appearance

**Files:**
- Modify: `modules/storyboard.py:65-83` (`build_edit_prompt`), `:122-147` (`build_continuity_prompt`)
- Modify: `tests/modules/test_storyboard.py`

**Interfaces:**
- Consumes: `character_is_absent(shot_prompt) -> bool` (existing, unchanged).
- Produces:
  - `build_edit_prompt(shot_prompt: str, style: str, appearance: str | None = None) -> str`
  - `build_continuity_prompt(shot_prompt: str, style: str, appearance: str | None = None) -> str`
  - `_appearance_block(appearance: str) -> str` — module-level helper, the single source of the injected wording

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_storyboard.py`:

```python
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
    before = build_continuity_prompt("Kenji lunges forward", "anime")
    after = build_continuity_prompt("Kenji lunges forward", "anime", None)

    assert before == after
    assert "always looks exactly like this" not in before


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


def test_the_appearance_block_asserts_authority_over_the_scene():
    prompt = build_edit_prompt("Sora wades forward", "anime", APPEARANCE)
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_storyboard.py -k appearance -v`
Expected: FAIL — `build_edit_prompt() takes 2 positional arguments but 3 were given`

- [ ] **Step 3: Write the implementation**

In `modules/storyboard.py`, add above `build_edit_prompt`:

```python
def _appearance_block(appearance: str) -> str:
    """The locked character description, stated as an overriding instruction.

    This exists because of a measured failure: the edit prompt described the
    scene in rich language and the character only in pixels, and probing
    established that when the image and the text disagree, the TEXT wins. So the
    character loses its costume to whatever the scene implies. Describing the
    character in words too — first, and marked authoritative — puts it back on
    equal footing.

    Placement is load-bearing, not cosmetic: this goes ahead of the
    reference-image and style instructions, not appended after the scene.
    """
    return (
        f"THE CHARACTER ALWAYS LOOKS EXACTLY LIKE THIS, in every shot, regardless "
        f"of what the scene describes: {appearance} "
        f"This description is the AUTHORITY on the character's face, hair, clothing "
        f"and accessories. The scene below says what happens and where — it does NOT "
        f"change how the character looks. If the scene implies different clothing, "
        f"ignore that and keep the description above. "
    )
```

Replace `build_edit_prompt` (lines 65-83) with:

```python
def build_edit_prompt(
    shot_prompt: str, style: str, appearance: str | None = None
) -> str:
    """The instruction handed to GPT Image 2 Edit for one shot.

    `appearance` is the locked character description in words. It is omitted for
    character-absent shots, where there is no character in frame to describe.
    """
    if character_is_absent(shot_prompt):
        return (
            f"Use the reference image as a STYLE anchor only — preserve the {style} "
            f"illustration style, color palette, and the world established in the reference. "
            f"The main character should NOT be in frame for this shot (it is a POV, "
            f"wide-exterior, or environmental shot). Render the scene exactly as the shot "
            f"prompt describes, as a 9:16 vertical still frame at the START of the action, "
            f"no motion blur. Scene: {shot_prompt}"
        )
    lead = _appearance_block(appearance.strip()) if appearance and appearance.strip() else ""
    return (
        f"{lead}"
        f"Use the reference image as the base — preserve the main character's face, "
        f"hair, outfit, and {style} style exactly. Render this scene as a 9:16 "
        f"vertical still frame at the START of the action, no motion blur. If the shot "
        f"prompt explicitly names other characters or entities (a holographic AI "
        f"manifesting as light, another person, a creature), include them rendered "
        f"exactly as the shot prompt describes. Scene: {shot_prompt}"
    )
```

Replace `build_continuity_prompt` (lines 122-147) with:

```python
def build_continuity_prompt(
    shot_prompt: str, style: str, appearance: str | None = None
) -> str:
    """The instruction for a two-base edit.

    Probing showed the model resolves conflicts toward the TEXT, so precedence
    between the two images has to be stated rather than implied — and so the
    locked appearance, when supplied, is stated in text rather than left to the
    reference image's pixels.
    """
    if character_is_absent(shot_prompt):
        return (
            f"You are given two images. The FIRST is a STYLE anchor — preserve the "
            f"{style} illustration style, colour palette and world from it. The SECOND "
            f"is the final moment of the previous shot — match its lighting, weather "
            f"and time of day so the two shots feel continuous. The main character "
            f"should NOT be in frame for this shot (it is a POV, wide-exterior, or "
            f"environmental shot). Render the scene as a 9:16 vertical still frame at "
            f"the START of the action, no motion blur. Scene: {shot_prompt}"
        )
    lead = _appearance_block(appearance.strip()) if appearance and appearance.strip() else ""
    return (
        f"{lead}"
        f"You are given two images. The FIRST image is the authority on WHO the "
        f"character is — preserve their face, hair, eye colour, outfit and the {style} "
        f"style from it exactly. The SECOND image is the final moment of the previous "
        f"shot — use it for continuity of lighting, weather, wardrobe state and where "
        f"other characters are standing, and keep any second character looking exactly "
        f"as they do there. Where the two images disagree about the main character's "
        f"appearance, the FIRST image wins. Render this scene as a 9:16 vertical still "
        f"frame at the START of the action, no motion blur. Scene: {shot_prompt}"
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_storyboard.py -v`
Expected: all PASS, including every pre-existing prompt test

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: 301 passed + the new tests, 4 skipped

- [ ] **Step 6: Commit**

```bash
git add modules/storyboard.py tests/modules/test_storyboard.py
git commit -m "feat: storyboard prompts can state the locked appearance in words

The edit prompt described the scene in rich language and the character
only in pixels, and probing established the text wins on conflict --
so the costume lost to whatever the scene implied. Describing the
character in words too, first and marked authoritative, puts it back
on equal footing.

Omitted for character-absent shots, where there is no character in
frame to describe. Byte-identical when no appearance is supplied.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The suppliers thread the appearance through

**Files:**
- Modify: `modules/storyboard.py:86-119` (`build_storyboards`), `:150-214` (`ChainedStoryboards`)
- Modify: `tests/modules/test_storyboard.py`

**Interfaces:**
- Consumes: `build_edit_prompt(shot_prompt, style, appearance=None)`, `build_continuity_prompt(shot_prompt, style, appearance=None)` (Task 1).
- Produces:
  - `build_storyboards(shots, reference_image_url, *, style, appearance=None, generator=None, log=None) -> list[str | None]`
  - `ChainedStoryboards(reference_image_url, *, style, appearance=None, generator=None, log=None)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_storyboard.py`:

```python
def test_build_storyboards_passes_the_appearance_to_every_shot():
    editor = StubEditor()

    build_storyboards(
        ["Alan turns from the console", "She walks the corridor"],
        "https://cdn/alan.png",
        style="anime", appearance=APPEARANCE,
        generator=editor, log=lambda _: None,
    )

    for _, prompt in editor.calls:
        assert APPEARANCE in prompt


def test_build_storyboards_without_an_appearance_is_unchanged():
    with_none = StubEditor()
    build_storyboards(
        ["Alan turns from the console"], "https://cdn/alan.png",
        style="anime", generator=with_none, log=lambda _: None,
    )

    assert APPEARANCE not in with_none.calls[0][1]
    assert "always looks exactly like this" not in with_none.calls[0][1].lower()


def test_chained_storyboards_injects_the_appearance_on_the_first_shot():
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", appearance=APPEARANCE,
        generator=editor, log=lambda _: None,
    )

    supplier.frame_for(0, "Sora wades forward", None)

    assert APPEARANCE in editor.calls[0][1]


def test_chained_storyboards_injects_the_appearance_on_chained_shots(monkeypatch, tmp_path):
    clip = tmp_path / "shot_00.mp4"
    clip.write_bytes(b"fake")
    monkeypatch.setattr("modules.storyboard.extract_last_frame", lambda path, **kw: str(clip))
    monkeypatch.setattr("modules.storyboard.to_data_uri", lambda path, **kw: "data:image/png;base64,ZZZ")
    editor = ListEditor()
    supplier = ChainedStoryboards(
        "https://cdn/ref.png", style="anime", appearance=APPEARANCE,
        generator=editor, log=lambda _: None,
    )

    supplier.frame_for(1, "Sora shoves the figure", str(clip))

    base, prompt = editor.calls[0]
    assert base == ["https://cdn/ref.png", "data:image/png;base64,ZZZ"]
    assert APPEARANCE in prompt
    assert "two images" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_storyboard.py -k "passes_the_appearance or injects_the_appearance" -v`
Expected: FAIL — `build_storyboards() got an unexpected keyword argument 'appearance'`

- [ ] **Step 3: Write the implementation**

In `build_storyboards`, add the parameter after `style` and pass it on:

```python
def build_storyboards(
    shots: list[str],
    reference_image_url: str,
    *,
    style: str,
    appearance: str | None = None,
    generator: ImageEditor | None = None,
    log: Callable[[str], None] | None = None,
) -> list[str | None]:
```

and change the prompt line inside the loop from
`prompt = build_edit_prompt(shot_prompt, style)` to:

```python
        prompt = build_edit_prompt(shot_prompt, style, appearance)
```

In `ChainedStoryboards.__init__`, add the parameter after `style` and store it:

```python
    def __init__(
        self,
        reference_image_url: str,
        *,
        style: str,
        appearance: str | None = None,
        generator: ImageEditor | None = None,
        log: Callable[[str], None] | None = None,
    ):
        if generator is None:
            from modules.image_generator import AtlasImageGenerator
            generator = AtlasImageGenerator()
        self._reference = reference_image_url
        self._style = style
        self._appearance = appearance
        self._generator = generator
        self._log = log or (lambda message: print(message, flush=True))
```

In `frame_for`, pass it to both builders:

```python
        prompt = build_edit_prompt(shot_prompt, self._style, self._appearance)
```

and inside the chaining `try`:

```python
                prompt = build_continuity_prompt(shot_prompt, self._style, self._appearance)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_storyboard.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: no failures

- [ ] **Step 6: Commit**

```bash
git add modules/storyboard.py tests/modules/test_storyboard.py
git commit -m "feat: both storyboard suppliers thread the locked appearance

Batch and chained paths both reach their prompt builder with the
appearance, so a preset gets the same character text whichever
anchoring mode it uses.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: preset-7 reads its locked paragraph from the characters sheet

**Files:**
- Modify: `modules/characters_reader.py` — add a method beside `get_main_ref_image_for_form` (currently at `:115-134`)
- Modify: `tests/modules/test_characters_reader.py`

**Interfaces:**
- Consumes: `CharactersReader.get_main_character() -> dict | None` (existing).
- Produces: `CharactersReader.get_main_appearance_for_form(character_form: str) -> str | None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/modules/test_characters_reader.py`. It already has everything
needed: the `configured` fixture (sets the env var), `_session(rows)` (an
in-memory characters tab), `_char(**overrides)` (a blank row with the real
headers), and the `ALAN` fixture row carrying both appearance columns. Reuse
them — do not add a new construction helper.

```python
# -- locked appearance, form-aware --------------------------------------------

def test_appearance_form_selection_mirrors_the_ref_image_logic(configured):
    """The same episode's character_form already picks the image; it must pick
    the matching words, or the prompt describes Alan while the image shows
    Zenith."""
    session, _ = _session([ALAN])
    reader = CharactersReader(session)

    assert reader.get_main_appearance_for_form("normal").startswith("Late 30s")
    assert reader.get_main_appearance_for_form("transformed").startswith("Crystalline")
    assert reader.get_main_appearance_for_form("both").startswith("Crystalline")
    assert reader.get_main_appearance_for_form("").startswith("Late 30s")


def test_appearance_selection_matches_ref_image_selection_for_every_form(configured):
    """Pins the mirror explicitly: whichever form picks the transformed IMAGE
    must pick the transformed WORDS."""
    session, _ = _session([ALAN])
    reader = CharactersReader(session)

    for form in ("normal", "transformed", "both", "", "nonsense"):
        image_is_transformed = (
            reader.get_main_ref_image_for_form(form) == "https://img/zenith.png"
        )
        words_are_transformed = reader.get_main_appearance_for_form(form).startswith(
            "Crystalline"
        )
        assert image_is_transformed == words_are_transformed, form


def test_appearance_falls_back_when_the_requested_form_is_empty(configured):
    session, _ = _session([_char(
        character_name="Alan Vorne", role="main",
        appearance_normal="Late 30s, dark coat.",
        appearance_transformed="",
    )])

    assert CharactersReader(session).get_main_appearance_for_form(
        "transformed"
    ).startswith("Late 30s")


def test_appearance_falls_back_the_other_direction_too(configured):
    session, _ = _session([_char(
        character_name="Alan Vorne", role="main",
        appearance_normal="",
        appearance_transformed="Crystalline plates.",
    )])

    assert CharactersReader(session).get_main_appearance_for_form(
        "normal"
    ).startswith("Crystalline")


def test_no_appearance_anywhere_returns_none(configured):
    session, _ = _session([_char(
        character_name="Alan Vorne", role="main",
        appearance_normal="", appearance_transformed="",
    )])

    assert CharactersReader(session).get_main_appearance_for_form("normal") is None


def test_no_main_character_returns_none(configured):
    session, _ = _session([MIRA])   # role="ally", not "main"

    assert CharactersReader(session).get_main_appearance_for_form("normal") is None


def test_appearance_is_none_when_the_sheet_is_not_configured(monkeypatch):
    """Mirrors the existing no-op guarantee for get_main_ref_image_for_form."""
    monkeypatch.delenv(ENV_VAR, raising=False)

    assert CharactersReader().get_main_appearance_for_form("normal") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/modules/test_characters_reader.py -k appearance -v`
Expected: FAIL — `'CharactersReader' object has no attribute 'get_main_appearance_for_form'`

- [ ] **Step 3: Write the implementation**

Add to `modules/characters_reader.py`, directly beneath `get_main_ref_image_for_form`:

```python
    def get_main_appearance_for_form(self, character_form: str) -> str | None:
        """Return the locked appearance paragraph for the main character matching
        the requested form ("normal" | "transformed" | "both").

        Deliberately mirrors get_main_ref_image_for_form's selection logic. The
        episode's character_form already chooses the reference image; it must
        choose the matching words, or the prompt describes Alan while the image
        shows Zenith.

        Selection logic:
        - "transformed" or "both" → appearance_transformed if set, else appearance_normal
        - "normal" or anything else → appearance_normal if set, else appearance_transformed
        - None if neither is set (signals the caller to inject no appearance)
        """
        main = self.get_main_character()
        if not main:
            return None
        normal = str(main.get("appearance_normal", "")).strip()
        transformed = str(main.get("appearance_transformed", "")).strip()

        form = (character_form or "").strip().lower()
        if form in ("transformed", "both"):
            return transformed or normal or None
        return normal or transformed or None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/modules/test_characters_reader.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add modules/characters_reader.py tests/modules/test_characters_reader.py
git commit -m "feat: locked appearance paragraph, form-aware

Mirrors get_main_ref_image_for_form exactly. The episode's
character_form already chooses the reference image; it must choose the
matching words, or the prompt describes Alan while the image shows
Zenith.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Wire the sources

**Files:**
- Modify: `orchestrator.py:292-303` (the storyboard block)
- Modify: `scripts/manual_episode.py:207-215` (the storyboard block)
- Modify: `tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `build_storyboards(..., appearance=...)` and `ChainedStoryboards(..., appearance=...)` (Task 2); `CharactersReader.get_main_appearance_for_form(form)` (Task 3).
- Produces: no new public API.

- [ ] **Step 1: Write the failing tests**

First, extend the existing `FakeCharactersReader` in `tests/test_orchestrator.py`
so it answers the new method. Without this, any test that flips
`serialized_canon=True` raises `AttributeError` instead of exercising the
branch:

```python
class FakeCharactersReader:
    available = False

    def __call__(self, session):
        return self

    def get_main_ref_image_for_form(self, form):
        return None

    def get_main_appearance_for_form(self, form):
        return None
```

Then append these tests. They use the file's existing `_deps`, `_row`,
`FakeVideoProducer`, `FakeGenerator`, `SCRIPT_RESULT`, `_explodes` and
`requires_shot_pipeline` helpers — do not invent new ones.

```python
# -- the locked appearance reaches the storyboard builders --------------------

@requires_shot_pipeline
def test_a_canon_preset_takes_the_appearance_from_the_characters_sheet(monkeypatch):
    """preset-7's locked paragraph is canon and stable across 200 episodes, so
    it beats the per-episode character_image_prompt."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=True,
            per_shot_storyboards=True,
            chain_reference_frames=False,
        ),
    )

    class Chars:
        available = True
        def __call__(self, session):
            return self
        def get_main_ref_image_for_form(self, form):
            return "https://cdn/zenith.png"
        def get_main_appearance_for_form(self, form):
            return "LOCKED PARAGRAPH FROM THE SHEET"

    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        characters=Chars(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "LOCKED PARAGRAPH FROM THE SHEET"


@requires_shot_pipeline
def test_a_non_canon_preset_takes_the_appearance_from_the_script(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image="https://cdn/ref.png",
        ),
    )
    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"


@requires_shot_pipeline
def test_a_canon_preset_falls_back_to_the_script_when_the_sheet_is_empty(monkeypatch):
    """A roster row with no appearance paragraph must not blank the prompt."""
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=True,
            per_shot_storyboards=True,
            chain_reference_frames=False,
            default_ref_image="https://cdn/ref.png",
        ),
    )

    class EmptyChars:
        available = True
        def __call__(self, session):
            return self
        def get_main_ref_image_for_form(self, form):
            return None
        def get_main_appearance_for_form(self, form):
            return None

    seen = {}
    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        characters=EmptyChars(),
        storyboards=lambda shots, ref, **kw: seen.update(kw) or [None] * len(shots),
        chained_storyboards=_explodes("the chained storyboard supplier"),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"


@requires_shot_pipeline
def test_a_chaining_preset_also_receives_the_appearance(monkeypatch):
    import orchestrator
    monkeypatch.setattr(
        orchestrator, "_preset",
        replace(
            orchestrator._preset,
            serialized_canon=False,
            per_shot_storyboards=True,
            chain_reference_frames=True,
            default_ref_image="https://cdn/ref.png",
        ),
    )
    seen = {}

    class SpySupplier:
        def frame_for(self, index, shot_prompt, previous_clip):
            return None

    deps, _ = _deps(
        [_row(story_brief="b", status="pending")],
        script=FakeGenerator({**SCRIPT_RESULT,
                              "character_image_prompt": "GENERATED CHARACTER PROMPT"}),
        storyboards=_explodes("the batch storyboard builder"),
        chained_storyboards=lambda ref, **kw: seen.update(kw) or SpySupplier(),
    )

    run_pipeline(deps)

    assert seen["appearance"] == "GENERATED CHARACTER PROMPT"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_orchestrator.py -k appearance -v`
Expected: FAIL — `seen["appearance"]` is `None`, because nothing supplies it yet

- [ ] **Step 3: Write the implementation**

Replace the storyboard block in `orchestrator.py` (lines 292-303) with:

```python
        # The locked appearance, in words. The reference image alone loses the
        # costume: the edit prompt describes the scene richly and the character
        # only in pixels, and the model resolves that conflict toward the text.
        # Canon presets have a locked paragraph on the characters sheet; the
        # rest have the prompt that generated their reference image.
        appearance: str | None = None
        if _preset.serialized_canon:
            appearance = deps.characters(session).get_main_appearance_for_form(
                str(episode.character_form).strip().lower() or "normal"
            )
        if not appearance:
            appearance = script_result.get("character_image_prompt")

        storyboard_urls: list[str | None] | None = None
        storyboard_supplier = None
        if _preset.per_shot_storyboards and ref_image_url:
            if _preset.chain_reference_frames:
                storyboard_supplier = deps.chained_storyboards(
                    ref_image_url, style=VIDEO_STYLE, appearance=appearance,
                )
                print("[Pipeline] Chained storyboards enabled", flush=True)
            else:
                storyboard_urls = deps.storyboards(
                    script_result["shots"], ref_image_url,
                    style=VIDEO_STYLE, appearance=appearance,
                )
```

In `scripts/manual_episode.py`, the storyboard block already runs after the
reference image is resolved, and `char_prompt` is only bound inside the
`if not ref_image_url:` branch. Hoist it so it is always available: initialise
`char_prompt = None` before that branch, and when the sheet already supplies a
`ref_image_url`, fall back to `script_result.get("character_image_prompt")` when
a script was generated. Then pass it:

```python
    if args.chain:
        print("\n[3/4] Chained storyboards — each shot sees the previous frame")
        storyboard_supplier = ChainedStoryboards(
            ref_image_url, style=VIDEO_STYLE, appearance=char_prompt,
        )
    elif not args.no_storyboards:
        print("\n[3/4] Generating per-shot storyboards...")
        storyboard_urls = build_storyboards(
            shots, ref_image_url, style=VIDEO_STYLE, appearance=char_prompt,
        )
```

Read the surrounding code before editing — `char_prompt` must be defined on
every path that reaches the storyboard block, including `--dry-run` returning
early and the inline-shots path where no `script_result` exists.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_orchestrator.py -v`
Expected: all PASS

- [ ] **Step 5: Verify the entry points still import**

Run: `python3 -c "import orchestrator, main" && python3 scripts/manual_episode.py --help`
Expected: no traceback; help text unchanged apart from what Task 4 touched

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest tests -q`
Expected: no failures

- [ ] **Step 7: Commit**

```bash
git add orchestrator.py scripts/manual_episode.py tests/test_orchestrator.py
git commit -m "feat: supply the locked appearance to every storyboard preset

Canon presets read the locked paragraph from the characters sheet,
form-aware so Alan's words match Alan's image. Everything else reuses
the character_image_prompt that generated its reference image and was
then discarded.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Storyboard-only A/B verification

The chaining verification cost ~$1.90 and returned n=1. This one costs ~$0.18 and returns three samples per arm, because the defect is visible in the storyboard still — no video generation required.

**Files:**
- Create: `docs/superpowers/plans/2026-08-03-locked-appearance-injection-results.md`

**Interfaces:**
- Consumes: everything from Tasks 1-4.
- Produces: a verdict on whether the injected arm preserves the reference's named garments.

- [ ] **Step 1: Confirm the pinned inputs from the previous run are still available**

The chaining A/B cached its script and reference image. Reusing them keeps this
comparison controlled and costs nothing.

Run: `python3 -c "import json,os; p=os.environ.get('PINNED','/tmp/pinned_inputs.json'); d=json.load(open(p)); print(len(d['shots']),'shots;',d['ref_image_url'][:70])"`
with `PINNED` set to the `pinned_inputs.json` path from the chaining run.
Expected: 5 shots and a reference URL. If the file is gone, regenerate it with
that run's `prep` step (~$0.04) before continuing.

- [ ] **Step 2: Write the comparison harness**

A scratchpad script that, for each of three samples per arm, calls
`build_storyboards` over the pinned shots — control arm with no `appearance`,
injected arm with the pinned `character_image_prompt` — and downloads the
resulting stills. Six arms × 5 shots × $0.006 = ~$0.18.

Do **not** generate video. The defect under test is in the still.

- [ ] **Step 3: Run it and build a contact sheet per arm**

```bash
ffmpeg -y -v error -i sample_%02d.png -vf "scale=260:-1,tile=5x1" arm_grid.jpg
```

- [ ] **Step 4: Score against the reference's named features**

The pinned reference describes: **short black hair, worn yellow sweatband,
orange maintenance jumpsuit, white fitted shirt, black rubber gloves, utility
belt with a cracked flashlight.**

For each of the 30 stills, record which of those six features are present.
Report per-arm totals, not impressions.

- [ ] **Step 5: Write and commit the results**

Record the per-feature counts, the verdict, and — if the injected arm wins —
whether it wins on shot 1 specifically, since that is the shot that proved the
defect. Save to
`docs/superpowers/plans/2026-08-03-locked-appearance-injection-results.md`.

```bash
git add docs/superpowers/plans/2026-08-03-locked-appearance-injection-results.md
git commit -m "docs: storyboard A/B results for locked appearance injection

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Spec Coverage

| Spec section | Task |
|---|---|
| §3.1 Both builders accept `appearance` | Task 1 |
| §3.1 Byte-identical when absent | Task 1 (asserted against literal strings) |
| §3.1 Block placed first, marked authoritative | Task 1 |
| §3.2 Both suppliers thread it | Task 2 |
| §3.3 `get_main_appearance_for_form`, form-aware | Task 3 |
| §3.4 Canon presets read the sheet | Task 4 |
| §3.4 Others use `character_image_prompt` | Task 4 |
| §3.4 No config flag | Task 4 (no capability added) |
| §4 Missing source degrades silently | Tasks 1, 4 |
| §5 Unit tests, no network | Tasks 1-4 |
| §6 Storyboard-only A/B, 3 samples per arm | Task 5 |
| Constraint: never inject on character-absent shots | Task 1 |
