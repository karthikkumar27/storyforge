# Chained Reference Frames — fixing character drift across shots

**Date:** 2026-08-03
**Status:** Approved, ready for implementation planning
**Scope:** preset-9 (Modern Shōnen Action) only. preset-7 remains unchanged.

---

## 1. The problem

Published preset-9 episode *"Half a Word Left"*
([JRUrow6Akyc](https://youtube.com/shorts/JRUrow6Akyc), 40.3s, five 8.06s shots)
shows the lead character rendered two different ways inside one video:

- Shots 2–3: violet eyes, black/purple sailor uniform, purple neckerchief.
- Shot 5: bright blue eyes, navy-and-white sailor uniform with a circular chest
  emblem, visibly flatter and brighter cel style.

A viewer cannot tell whether the payoff close-up is the protagonist or the rival.

This happened **despite** first-frame anchoring already being switched on.
preset-9 sets `per_shot_storyboards: True` (`config.py:397`), so every shot —
not just shot 1 — was handed a GPT Image 2 Edit still as its Seedance first
frame.

### Root causes

Three distinct causes. This spec fixes the first, partially mitigates the
second, and leaves the third alone:

1. **Storyboards are mutually blind.** `build_storyboards`
   (`modules/storyboard.py:80`) generates every shot's still independently from
   the same base reference. No storyboard can see what the previous shot
   actually rendered, so each is free to re-interpret eye colour, palette, and
   line style within the reference's tolerance.

2. **Only one character is anchored.** `build_edit_prompt`
   (`modules/storyboard.py:71`) instructs the model to preserve *"the main
   character's face, hair, outfit"* — singular. A `rival-showdown` has two
   leads. The second is reinvented from scratch on every shot because nothing
   anchors them.

3. **Seedance drifts within a clip.** Identity at second 8 of a shot is further
   from the reference than at second 0. Out of scope here; noted because it
   dictates a design constraint in §3.

---

## 2. Capability probe results

Run against Atlas Cloud on 2026-08-03. Total cost ~$0.21. These findings
constrain the design and are recorded so they need not be re-bought.

| Question | Result |
|---|---|
| Does `bytedance/seedance-v1.5-pro/image-to-video-fast` honour `return_last_frame`? | **No.** The field is accepted without error and silently ignored — one output with the flag, one without, byte-identical behaviour. Atlas does not host a last frame for us. |
| Can a locally-held frame reach the edit endpoint without a bucket? | **Yes.** `image: "data:image/png;base64,…"` completes normally. No cloud storage dependency required. |
| Can `openai/gpt-image-2/edit` take two base images? | **Yes.** Both `image: [a, b]` and `images: [a, b]` complete. `image_urls` is rejected with `request body field <image> is required`. |
| Does a two-image edit respect `width`/`height`? | **No.** Returned 1536×1024 landscape on both variants despite `width: 768, height: 1344`. |

### Incidental finding (out of scope, needs its own ticket)

Atlas intermittently fails `openai/gpt-image-2/text-to-image` with
`Unknown parameter: 'height'` — a misleading schema error for a body that
succeeds minutes later unchanged. Observed repeatedly across different prompts
during probing. `ImageGenerator.generate()` retries 3× and then raises, which
hard-fails the entire episode. Recommend adding a size-parameter fallback ladder
(`width`/`height` → `size` → omit) and treating this error as transient. Not
part of this work.

---

## 3. Design

### 3.1 Mechanism — dual-base storyboards

From shot 2 onward, each storyboard edit receives **two** base images:

```
shot N-1 clip ──ffmpeg──► last clean frame ──base64──┐
                                                     ├─► edit([ref, prev]) ─► 9:16 ─► shot N
locked reference image ──────────────────────────────┘
```

- **Position 1 — the locked reference image.** The authority on who the
  character is.
- **Position 2 — the previous shot's last clean frame.** Continuity: lighting
  state, wardrobe state, rain, where the rival is standing, how far the fight
  has progressed.

Every storyboard therefore stays exactly **one generation removed from the
locked reference**. Drift is corrected against the reference on every shot
instead of accumulating forward. This is a deliberate rejection of naive
chaining (frame N−1 as the sole base), which would put shot 5 four generations
from the reference and violate the two-generation rule in the
`character-consistency` skill. Cause 3 above is precisely why: the last frame of
a clip is the most drifted frame in it, so it must never be the sole authority.

Hard cuts are preserved. The shot prompt still drives framing, so the pipeline
retains its freedom to cut between wide, POV, and close-up. This is not a
continuous-take mode.

**Secondary benefit:** this partially addresses root cause 2 at no extra cost.
There is no locked reference for the rival, but the rival appears *in the
previous frame*. Chaining gives the next storyboard a visual anchor for a
character the current architecture cannot anchor at all.

### 3.2 Control flow inversion

This is the substantive structural change.

Today all storyboards are generated in one batch **before** any video exists:
`orchestrator.py:288` calls `build_storyboards`, which returns a complete list
of URLs, which is then passed to `produce()` as `storyboard_urls`.

Chaining makes storyboard N depend on shot N−1's rendered clip, so the two loops
must interleave. Rather than moving image generation inside the video producer —
which would fuse two currently-separate responsibilities — `produce()` gains a
**supplier** it calls once per shot:

```python
class StoryboardSupplier(Protocol):
    """Yields the first-frame still for one shot, given what came before."""
    def frame_for(self, index: int, shot_prompt: str,
                  previous_frame: str | None) -> str | None: ...
```

`previous_frame` is `None` for shot 1. A `None` return means "no storyboard for
this shot" and the producer falls back to the shared reference image, exactly as
it does today when `storyboard_urls[i]` is `None`.

The existing `storyboard_urls: list[str | None]` parameter is retained for
presets that do not chain and for tests. The supplier is additive and optional;
when both are absent, behaviour is byte-identical to today.

### 3.3 Components

| File | Change |
|---|---|
| `modules/frame_chain.py` *(new)* | `extract_last_frame(clip_path) -> str` — ffmpeg, sampled 0.4s before the end to avoid motion blur and fade-outs. `to_data_uri(path) -> str` — downscales the longest edge to 768px before encoding, keeping the payload near 300KB (the size proven to work in probing). `normalise_portrait(path) -> str` — centre-crop to 9:16. |
| `modules/storyboard.py` | Chained variant of `build_storyboards` implementing `StoryboardSupplier`. `build_edit_prompt` gains wording naming which base is identity and which is continuity. |
| `modules/image_generator.py` | `edit_image` accepts `str \| list[str]` for the base image. |
| `modules/video_producer.py` | `produce()` accepts an optional supplier and calls it per shot, passing the previous clip's extracted frame. |
| `orchestrator.py` | Wires the supplier when the active preset opts in. |
| `config.py`, `modules/preset.py` | New capability `chain_reference_frames: bool`, defaulting to `False`. Data, not an identity check — consistent with the capability pattern documented in `preset.py`. |

### 3.4 Prompt wording

`build_edit_prompt` must distinguish the two bases explicitly, because the probe
showed **text wins over images when they conflict** (see §5). The instruction
should state that the first image is the authority on character identity, that
the second shows the immediately preceding moment and supplies continuity of
lighting/wardrobe/staging, and that where the two disagree on appearance the
first image wins.

### 3.5 Aspect ratio handling

The API cannot be trusted to frame the output — a two-image edit returned
landscape while asking for portrait. The pipeline therefore **verifies and
corrects locally**: every storyboard is passed through `normalise_portrait()`
before it becomes a Seedance first frame, regardless of what the API returned.
This also insulates the pipeline against Atlas changing these defaults again.

Correction is **centre-crop, never letterbox**. A letterboxed still would carry
black bars into the first frame, and Seedance would treat those bars as scene
content and propagate them through the entire generated clip. Cropping loses
edge detail; letterboxing would poison the shot.

---

## 4. Failure handling

Every failure degrades to today's behaviour rather than failing the episode —
the same philosophy `build_storyboards` already applies when an edit fails.

| Failure | Behaviour |
|---|---|
| Frame extraction fails (corrupt/short clip) | Fall back to a single-base storyboard for that shot. That shot loses continuity; the episode continues. |
| Edit returns non-portrait | Centre-crop to 9:16 locally, log at warning level. |
| Data URI exceeds the size cap | Downscale the frame before encoding. |
| Atlas edit fails outright | Existing retry in `edit_image`, then fall back to the locked reference. |
| Supplier raises unexpectedly | Caught per shot; falls back to the locked reference. One shot degrades, not the run. |

---

## 5. Risks

**Two-base fidelity is unproven.** The probe that established multi-image
support deliberately fed the model a contradiction (text naming an object absent
from the images) and the **text dominated** — the output rendered what the
prompt described, not what the source images showed, and in a different visual
style. This does not prove the model ignores base images generally, but it does
mean faithfulness of the two-base call is not established. The implementation
plan must include a real before/after on one preset-9 episode before this is
considered working, and before it is considered for preset-7.

**Interleaving changes wall-clock shape.** Storyboard generation now happens
between video polls rather than up front. Total latency should be comparable
since both loops were already serial, but this should be observed rather than
assumed.

---

## 6. Testing

**Unit, with fakes, no network** — mirroring `tests/modules/test_storyboard.py`
and `tests/modules/test_video_producer.py`:

- Supplier receives `None` as `previous_frame` for shot 1 and shot N−1's
  extracted frame for every subsequent shot.
- Frame extraction targets an offset before the clip end, not the final frame.
- `normalise_portrait` centre-crops a landscape input to 9:16, adds no bars,
  and leaves a correct portrait input untouched.
- `edit_image` accepts a list of base images as well as a single string.
- Each failure path in §4 falls back rather than raising.
- With neither supplier nor `storyboard_urls`, `produce()` behaves exactly as
  before.

**Manual verification:** one preset-9 episode through
`scripts/manual_episode.py`, before and after, compared frame-by-frame using an
ffmpeg contact sheet. Success means the lead character's eye colour, uniform,
and art style are stable from shot 1 through shot 5.

---

## 7. Rollout

`chain_reference_frames` defaults to `False`. Enabled for preset-9 only.
preset-7 stays off until the manual before/after in §6 demonstrates fidelity —
it is a 200-episode series with locked canon and is not the place to discover
that the two-base call is unfaithful.

---

## 8. Cost

Unchanged at roughly **$1.10 per episode**. The chained edit is the same single
edit call per shot that already runs, with a second base image attached. Frame
extraction is local ffmpeg work and costs nothing.
