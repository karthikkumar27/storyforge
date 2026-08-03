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

**Amended 2026-08-03 after the Task 4 review — see §3.5.** The appearance and the
reference image must be a *pair*; the priority chain below never injects a
description that did not produce the image in hand.

| Priority | Source | Why it is safe |
|---|---|---|
| 1 | `serialized_canon` presets: `chars.get_main_appearance_for_form(form)` | Canon locked pair — `ref_image_normal` and `appearance_normal` live in the same sheet row and cannot disagree |
| 2 | The episode's saved `character_appearance` column | Written in the same call that saved `ref_image_url`, so it describes exactly that image |
| 3 | This run's `character_image_prompt` — **only when this run generated the reference image** | Prompt and image are aligned by construction |
| 4 | `None` | An un-described image is safer than a mis-described one |

### 3.5 Why the pair must travel together

The first draft of this design injected `character_image_prompt` whenever one
was available. The Task 4 review found that this can *invert* the fix.

`scripts/manual_episode.py` saves a generated reference image back to the sheet
precisely so a rerun reuses it. On that rerun the script generator produces a
**fresh** `character_image_prompt` — it is non-deterministic, so it may describe
a different character. Injecting that text as the authority, ahead of the image,
would let newly-invented words override the saved reference image that exists to
keep the character stable. Before this feature, no text was injected and the
image governed; the naive design would have made reruns *worse*. The same shape
exists for series presets reusing Part 1's image.

The remedy generalises what preset-7 already does. Its characters sheet stores
`ref_image_normal` beside `appearance_normal` — a locked pair that cannot drift
apart. Every other preset generated a prompt, made an image from it, saved the
image, and discarded the words. So a new `character_appearance` column is
written in the same `record()` call that saves `ref_image_url`, and read back
whenever that image is reused.

Consequence for the pipeline's one persistent artefact: of the six images a
5-shot video generates (one reference, five storyboards), only the reference
survives between runs. It is the sole carrier of identity, so whatever describes
it must survive with it.

Existing rows have an empty `character_appearance`. They fall to priority 4 —
today's behaviour — rather than to a mismatched fresh prompt.

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
