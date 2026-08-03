# Chained Reference Frames — before/after results

**Date:** 2026-08-03
**Verdict:** Inconclusive on drift. Ship the machinery, but it does not fix the
problem on its own — the real bottleneck is upstream and is named in §5.

---

## 1. Method

The plan's original method (two `manual_episode.py` runs on the same sheet row)
was **abandoned before spending** because it was invalid: row 50 has no
`ref_image_url` and no inline shots, so each run would have regenerated both the
script and the reference image. BEFORE and AFTER would have been different
stories starring different-looking characters, and any drift difference would
have been unattributable.

Replaced with a harness that pins the confounds:

- Script generated **once** (5 shots), shared verbatim by both passes
- Reference image generated **once**, shared by both passes
- Only the anchoring differs: `build_storyboards` vs `ChainedStoryboards`
- No writes to the Google Sheet

Source: row 50, genre `sealed-enemy`, preset-9. Chosen because the brief has
**two** characters (Sora and a silent doppelgänger), which is the case a single
locked reference cannot anchor.

Cost: ~$1.90 (prep $0.04, each pass ~$0.93).

## 2. The chaining machinery works

Verified from the run logs, not inferred:

| Check | Result |
|---|---|
| Shots anchored to a chained storyboard | 5/5 |
| Shots that chained to the previous frame | 4 (shots 2-5; shot 1 correctly uses the reference alone) |
| Inline anchors rejected by Atlas | **0** |
| Anchor payload sizes accepted | 1070KB, 1092KB, 1148KB, 1279KB at 576×1024 |
| Shrink-retry ladder fired | never |
| Both outputs | 40.23s, identical structure |

The edit endpoint also accepted the extracted previous frame as a second base
(`base: https://…a-b345956 + <inline 536KB>`), confirming both halves of the
mechanism against the real API.

**This resolves the spec §5 payload risk.** Atlas accepts ~1.1-1.3MB inline
payloads on `model/generateVideo` — roughly 3× the 391KB the original probe
proved, and above the 600-650KB the final review estimated. `ANCHOR_MAX_EDGE_PX
= 1024` is safe. The shrink rung remains as insurance and cost nothing.

## 3. What the frames actually show

Compared at each shot's midpoint (4s, 12s, 20s, 28s, 36s).

The reference image defines Sora as: **short black hair, worn yellow sweatband,
oversized orange maintenance jumpsuit unzipped to the waist over a white fitted
shirt, black rubber gloves, utility belt with a cracked flashlight.**

| Shot | BEFORE | AFTER |
|---|---|---|
| 1 | Black jacket, teal accents, shorts. No sweatband, no jumpsuit. | Same drift — black jacket, shorts, long hair. |
| 2 | Sailor-uniform figure; Sora seen from behind, black jacket | Sailor-uniform figure; Sora from behind with **silver hair** |
| 3 | POV, black fingerless glove | POV, black fingerless glove (different design) |
| 4 | Dark mass, water explosion | White explosion, no clear character |
| 5 | Yellow headband ✓, black crop top ✗ | **Yellow headband ✓, orange jumpsuit ✓, white shirt ✓, black gloves ✓, utility belt ✓ — plus the doppelgänger correctly rendered as a second identical Sora** |

AFTER's payoff shot is dramatically more faithful to the locked reference than
BEFORE's, and is the only frame in either run that renders the story's central
beat (two identical Soras) correctly.

## 4. Why this is not yet a win

**Sample size is one, and image generation is non-deterministic.** BEFORE and
AFTER used the *same* reference for shot 5's storyboard. BEFORE got the
sweatband but not the jumpsuit; AFTER got everything. That difference is
consistent with chaining helping, and equally consistent with one lucky sample.
Attributing it to the feature on n=1 would be wishful.

**Shots 1-4 drift in both passes, similarly.** No visible improvement.

## 5. The actual root cause — upstream of this entire feature

Shot 1 is generated **identically** by both methods: a single edit from the
locked reference, no chaining involved. And in both passes it already loses the
orange jumpsuit and the yellow sweatband, replacing them with a black jacket and
shorts.

That is decisive. If the very first storyboard — edited directly from the
reference, with `build_edit_prompt` explicitly instructing *"preserve the main
character's face, hair, outfit … exactly"* — already discards the costume, then
**the lossy step is the edit, not the absence of chaining.** Chaining then
faithfully propagates whatever shot 1 established, which is a character the
reference never described.

The probe finding in spec §2 predicts this: when the image and the text
disagree, **the text wins**. `build_edit_prompt` describes the *scene* in detail
and the *costume* not at all, so the model has rich words for the environment
and only pixels for the character — and the words win.

### Recommended next change

Inject the locked appearance **as text** into the storyboard edit prompt, not
just as a base image. For preset-9 that is the `character_image_prompt` the
script generator already produces; for preset-7 it is the locked appearance
paragraph already held in the characters sheet. This costs nothing per episode
and attacks the failure at its actual source.

Chaining should stay — it is cost-neutral, it is the only mechanism that can
anchor a *second* character (which no reference image covers), and shot 5 is
suggestive. But it should be re-measured after the prompt fix, with more than
one sample.

## 6. Recommendation on rollout

- **Keep `chain_reference_frames: True` for preset-9.** It demonstrably runs
  correctly, costs nothing extra, and degrades safely.
- **Do not enable it for preset-7.** Spec §7's condition — a before/after
  demonstrating fidelity — is not met.
- **Do the prompt-injection fix next**, then re-run this comparison with three
  samples per arm before drawing conclusions about drift.
