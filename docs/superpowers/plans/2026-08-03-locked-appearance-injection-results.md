# Locked Appearance Injection — before/after results

**Date:** 2026-08-03
**Verdict:** **Confirmed.** The fix works, decisively and consistently across
three samples per arm. This is the change that fixes character drift.

---

## 1. Method

Storyboard stills only — no video. The defect lives in the still: shot 1's
storyboard already lost the costume before Seedance ever ran, so generating
video to observe it would have been ~30× more expensive for the same evidence.

- Script and reference image **pinned** from the chaining A/B; identical in both arms
- Only the prompt differs: `build_edit_prompt(shot, style)` vs `build_edit_prompt(shot, style, appearance)`
- **3 samples per arm**, directly addressing the chaining A/B's n=1 weakness
- 5 shots × 3 samples × 2 arms = 30 stills, ~$0.18
- No writes to the Google Sheet

Source: row 50, genre `sealed-enemy`, preset-9 — chosen because the brief has
two characters, which is the case a single reference image cannot anchor.

The reference image defines: **short black hair, worn yellow sweatband,
oversized orange maintenance jumpsuit unzipped to the waist over a white fitted
shirt, black rubber work gloves, utility belt with a cracked flashlight.**

**Built-in null hypothesis.** Shot 3 is a POV shot, so `character_is_absent()`
is True and the appearance is deliberately *not* injected. It should therefore
look the same in both arms — and it does (a black-gloved hand, a distant figure,
no costume to get right). If shot 3 had varied as much as the others, the result
would have been generation noise rather than the injection working.

## 2. The result

Scored across the 12 character-present stills per arm (shots 1, 2, 4, 5 × 3
samples). Shot 3 excluded as N/A by design.

| Reference feature | Control | Injected |
|---|---|---|
| Orange maintenance jumpsuit | **1 / 12** | **12 / 12** |
| Yellow sweatband | 4 / 12 | 12 / 12 |
| White fitted shirt | 3 / 12 | 12 / 12 |
| Black gloves | 5 / 12 | 12 / 12 |
| Utility belt / flashlight | 1 / 12 | 11 / 12 |

The control arm reproduced the published-video failure exactly: one sample got
shot 1 right and then lost the costume for the rest of the episode; the other
two samples never had it at all. Shot 2 rendered Sora as a spiky-haired figure
in a black jacket in all three samples. Shot 4 rendered a white-haired character
in two of three.

The injected arm put Sora in the orange jumpsuit, white shirt and yellow
sweatband in **every character-present still of every sample** — including
shot 2 seen from behind, shot 4 mid-action inside a water explosion, and shot 5's
close-up.

### Consistency across the video, not just accuracy per shot

This is the property that matters for the product. In the injected arm the
character is recognisably the same person in shots 1, 2, 4 and 5 of the same
sample. In the control arm she changes outfit, hair and sometimes apparent
gender between consecutive shots of the same episode.

## 3. Why it works

The chaining A/B established that the reference *image* alone loses the costume,
and that the cause is modality: the prompt gave the model rich language for the
scene and only pixels for the character, and probing had already shown **text
beats image on conflict**.

Injecting the locked appearance as text removes the asymmetry. The character is
now described in the same modality as the scene, first, and marked as
overriding. The model stops inventing an outfit because it has been told one.

The text was already being generated and thrown away: `character_image_prompt`
is what created the reference image. Nothing new is produced per episode.

## 4. Cost

| | |
|---|---|
| Per-episode cost change | **$0.00** — same number of API calls, longer prompt |
| Prompt length | 1222 → 2267 characters |
| This verification | ~$0.18 |

## 5. Incidental finding

GPT Image 2 Edit returns **1024×1024 square** for most storyboards regardless of
the requested `width`/`height` — 10 of 15 control stills and 14 of 15 injected.
This is not caused by the injection; both arms show it. `portrait_anchor`
centre-crops to 9:16 downstream, which is precisely why that function exists,
but it means roughly 44% of a square still's width is discarded before it
becomes a first frame. Worth revisiting whether the edit call can be persuaded
to return 9:16 directly, since cropping loses framing the model intended.

## 6. Recommendation

- **Ship it for all five storyboard presets** (preset-1, 2, 3, 7, 9), as
  designed. The effect is large, consistent, and costs nothing per episode.
- **preset-7 now clears the bar the chaining work could not.** Its appearance
  source is the locked canon paragraph in the characters sheet — strictly better
  than the per-episode generated text used here, because it is hand-written and
  stable across 200 episodes. If injection works this well with generated text,
  it should work at least as well with canon.
- **Keep chained reference frames on for preset-9.** The chaining A/B was
  inconclusive on drift, but chaining is cost-neutral, degrades safely, and is
  the only mechanism that can anchor a *second* character — which no single
  reference image covers. With the costume now stable, chaining's contribution
  to continuity can be measured properly in a future comparison.
- **Re-run the chaining A/B after this lands.** Its n=1 result was measured
  against a baseline where the costume was drifting anyway. That comparison is
  worth repeating now that the dominant source of variation is removed.
