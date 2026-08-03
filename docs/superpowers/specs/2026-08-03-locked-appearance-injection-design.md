# Locked Appearance Injection — design

**Date:** 2026-08-03
**Status:** Approved, ready for implementation planning
**Scope:** every preset with `per_shot_storyboards: True` — preset-1, 2, 3, 7, 9

---

## 1. The problem

The chained-reference-frames A/B run
(`docs/superpowers/plans/2026-08-03-chained-reference-frames-results.md`)
measured character drift on preset-9 and found the cause is **not** where the
chaining feature assumed.

Shot 1 is generated identically by both arms of that experiment — a single GPT
Image 2 Edit from the locked reference image, no chaining involved. In both
arms it already discarded the reference's costume:

| | |
|---|---|
| Reference image defines | short black hair, worn **yellow sweatband**, oversized **orange maintenance jumpsuit** over a white fitted shirt, black rubber gloves, utility belt |
| Shot 1 rendered | black jacket with teal accents, shorts, no sweatband, no jumpsuit |

`build_edit_prompt` explicitly instructs *"preserve the main character's face,
hair, outfit … exactly"* — and the model does not comply.

### Root cause

The probe recorded in the chaining spec §2 established that **when the image
and the text disagree, the text wins**. `build_edit_prompt` gives the model:

- rich, specific **words** describing the scene (lighting, camera, blocking,
  action)
- only **pixels** describing the character
- a generic instruction to "preserve the outfit", naming no actual garment

So the model has detailed language for the environment and none for the
costume, and the language wins. The character is re-invented per shot.

This affects **five of nine presets** — every one with
`per_shot_storyboards: True`, including preset-7, the 200-episode
locked-canon series. Chaining was never the variable.

## 2. The fix

Inject the locked appearance **as text** into the storyboard edit prompt, so
the character is described in the same modality the scene is.

The text already exists and is currently discarded:

- **preset-1/2/3/9** — `character_image_prompt`, written by the script
  generator to *create* the reference image, then binned once the image exists
- **preset-7** — the locked appearance paragraphs already held in the
  characters sheet (`appearance_normal` / `appearance_transformed`), which are
  canon and stable across the series rather than regenerated per episode

No new generation, no new dependency, no per-episode cost.

## 3. Design

### 3.1 Prompt builders

Both builders gain an optional `appearance` parameter:

```python
build_edit_prompt(shot_prompt: str, style: str, appearance: str | None = None) -> str
build_continuity_prompt(shot_prompt: str, style: str, appearance: str | None = None) -> str
```

When `appearance` is `None`, the returned prompt is **byte-identical to
today's**. This is a hard requirement: it is the regression guard for every
preset, and the fallback for any caller that cannot supply a source.

When `appearance` is present, an authoritative character block is placed
**first**, before the existing reference-image and style instructions:

> The character always looks exactly like this, in every shot, regardless of
> what the scene describes: *{appearance}*
>
> This description is the authority on the character's face, hair, clothing and
> accessories. The scene below says what happens and where — it does NOT change
> how the character looks. If the scene implies different clothing, ignore that
> and keep the description above.

Placement and emphasis are deliberate. The failure is that scene language
out-weighs character pixels; the remedy is character language placed earlier and
marked as overriding.

### 3.2 Suppliers

```python
build_storyboards(shots, reference_image_url, *, style, appearance=None, ...)
ChainedStoryboards(reference_image_url, *, style, appearance=None, ...)
```

Both thread `appearance` through to their prompt builder unchanged.

### 3.3 preset-7's source

New method on `CharactersReader`, mirroring the existing
`get_main_ref_image_for_form` exactly — same form-selection logic, same
fallback chain, reading the appearance columns instead of the URL columns:

```python
get_main_appearance_for_form(character_form: str) -> str | None
```

- `"transformed"` or `"both"` → `appearance_transformed` if set, else `appearance_normal`
- `"normal"` or anything else → `appearance_normal` if set, else `appearance_transformed`
- `None` when neither is set — caller falls back to no injection

Symmetry with the ref-image accessor matters: the same episode's `character_form`
already picks the image, and it must pick the matching words.

### 3.4 Wiring

| Caller | Source |
|---|---|
| `orchestrator.py`, `serialized_canon` presets | `chars.get_main_appearance_for_form(form)` |
| `orchestrator.py`, all other presets | `script_result.get("character_image_prompt")` |
| `scripts/manual_episode.py` | the `character_image_prompt` it already computes for reference-image generation |

No config flag. This is corrected behaviour, not an opt-in capability — it
directly serves the character-consistency goal every affected preset already
has.

## 4. Failure handling

`appearance` is optional at every level. A missing or empty source yields
today's prompt exactly. Nothing raises, nothing degrades below current
behaviour.

## 5. Testing

Unit, no network:

- appearance present → the text appears verbatim in the prompt, with the
  precedence wording, ahead of the scene
- appearance absent → prompt byte-identical to today (regression guard)
- both builders covered, and both the character-present and character-absent
  prompt modes
- `get_main_appearance_for_form` mirrors the ref-image form logic, including
  both fallback directions and the all-empty case
- orchestrator wiring: a `serialized_canon` preset reads the sheet; a
  non-canon preset uses `character_image_prompt`

## 6. Verification

**Storyboard-only A/B, not video.** The defect is visible in the storyboard
still — shot 1 lost the costume before Seedance ever ran. Generating stills
alone costs 5 × $0.006 = **$0.03 per arm** against ~$0.93 for a full video pass.

That is cheap enough to run **three samples per arm** (~$0.18 total), which
directly addresses the weakness of the chaining verification, whose n=1 result
could not be separated from noise.

Reuses the pinned script and reference image already cached from that run, so
only the prompt differs between arms.

Success: the reference's named garments and accessories survive into the
storyboard stills in the injected arm and not the control arm, across all three
samples.
