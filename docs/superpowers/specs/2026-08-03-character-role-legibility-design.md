# Character Role Legibility — design

**Date:** 2026-08-03
**Status:** Approved, ready for implementation planning
**Scope:** every preset with `per_shot_storyboards: True` — preset-1, 2, 3, 7, 9

---

## 1. The problem

A published episode is visually consistent but dramatically illegible: a viewer
cannot tell which character is the protagonist and which is the threat, so they
have nobody to support. For short-form video that is a retention problem —
audiences attach to a character within the first seconds or they leave.

Two concrete causes, both verified in the storyboard A/B run:

**The antagonist has no anchor at all.** The script generator emits exactly one
`character_image_prompt`, for the main character. Supporting characters get
locked appearances only for preset-7, from its characters sheet. For preset-1,
2, 3 and 9 the antagonist is reinvented on every shot — in one episode "the
figure" rendered as a frightened schoolgirl in shot 2 and a pale white-haired
body in shot 4.

**Screen position is not held.** `skills/screenplay-director/SKILL.md` already
teaches `BLOCKING: Hero = LEFT, Villain = RIGHT` held across all shots, but as
an illustrative example rather than a rule, so it drifts. In the same episode,
shot 2 has the threat entering from the LEFT and shot 4 has the protagonist on
the LEFT. Position therefore carries no information about who is who.

The locked-appearance work fixed identity for **one** character. This is the
same gap, one character along — plus the role signalling that identity alone
does not provide.

## 2. Evidence this approach works

The storyboard A/B for locked-appearance injection
(`docs/superpowers/plans/2026-08-03-locked-appearance-injection-results.md`)
measured the protagonist's costume at **1/12 stills in the control arm and
12/12 in the injected arm**, across three samples.

The mechanism is established: earlier probing showed that when the image and
the text disagree, **the text wins**. The prompt gave the model rich language
for the scene and only pixels for the character, so the scene won.

The antagonist's position is strictly worse — no pixels *and* no words. The
same lever should therefore move at least as far, at the same cost of zero.

## 3. Design

### 3.1 What the script generator declares

Two new fields alongside the existing `character_image_prompt`:

```
"antagonist_name":       "the figure"
"antagonist_appearance": "<locked description, pasted verbatim>"
```

`antagonist_name` is how every shot refers to them. It is the trigger that makes
injection deterministic rather than dependent on the model remembering to
describe the antagonist in each shot.

Both may be empty. Many stories have no antagonist — a `landscape-sweep` or a
`power-awakening` may have none — and an empty declaration must degrade to
exactly today's behaviour.

### 3.2 Where the contrast lives

Contrast is written **into the two locked descriptions**, not enforced per shot.
Because both are pasted verbatim into every shot they appear in, the contrast is
inherited by all five shots automatically.

The script generator is instructed to write:

| | Protagonist | Antagonist |
|---|---|---|
| Palette | warm, saturated, distinct from the environment | cold, desaturated, or absorbing the environment |
| Silhouette | clear and readable at thumbnail size | broken, obscured, or subtly wrong |
| Face | visible and expressive | hidden, shadowed, turned away, or wrong |

This is one instruction at script time, enforced by injection at storyboard
time. It costs nothing per episode.

### 3.3 The injection trigger

A small value object carries both fields and owns the detection:

```python
@dataclass(frozen=True)
class Antagonist:
    name: str
    appearance: str

    def appears_in(self, shot_prompt: str) -> bool: ...
```

`appears_in` is a pure function — a **case-insensitive substring match** of
`name` in the shot text, the same shape as the existing `character_is_absent()`.
Detection logic lives on the value object so it can be tested in isolation,
without an API call.

Substring matching makes the declared name's specificity load-bearing. A generic
name matches promiscuously: `"the man"` would fire on *"the manhole cover"*, and
`"it"` would fire on almost every shot ever written, injecting the antagonist's
description into shots they are not in — worse than no injection, because the
model may then draw them. Two guards:

- The script generator is instructed to declare a **distinctive** name: a proper
  noun, or a noun phrase of two or more words (`"the hollow figure"`, not
  `"the figure"`; `"Kenji"`, not `"the rival"`).
- Names shorter than four characters never match. `appears_in` returns False for
  them, and the empty-match warning in §4 fires, surfacing the bad declaration
  rather than silently mis-injecting.

`build_edit_prompt` and `build_continuity_prompt` gain an optional
`antagonist: Antagonist | None`. The antagonist block is injected only when:

- an `Antagonist` is supplied with a non-empty name and appearance, **and**
- `antagonist.appears_in(shot_prompt)` is True, **and**
- the shot is not character-absent (POV and wide-exterior shots describe nobody)

Otherwise the prompt is byte-identical to what it is today.

### 3.4 Blocking

Promote the existing convention from example to rule, in the script generator's
CRITICAL RULES:

- The protagonist holds one side of frame across every shot; the antagonist
  holds the other.
- A character changing sides must be written as an explicit crossing
  ("crosses from the LEFT to the RIGHT of frame"), never an unremarked swap.
- The POV shot is exempt — the protagonist is the camera.

This cannot be enforced in code; the pipeline does not know where a character
stands. It is a prompt rule, and its effect is measured in §6 rather than
asserted.

### 3.5 Preset-7

Its roster mechanism is unchanged — the script generator already pastes
supporting characters' locked appearances into shot prompts from the characters
sheet. preset-7 gains the contrast and blocking rules, and gains the antagonist
declaration when an episode's antagonist is not a roster character. No new sheet
columns.

## 4. The known weak link

Injection depends on the script generator referring to the antagonist by
`antagonist_name` consistently. If it writes "the figure" in shot 2 and "the
entity" in shot 4, shot 4 receives no injection and drifts — and the failure is
**silent**, because a missing injection looks exactly like today's behaviour.

Three mitigations, in order of strength:

1. **Instruction.** The generator is told to use `antagonist_name` verbatim in
   every shot the antagonist appears in — the discipline it already applies to
   the main character's name.
2. **A loud warning.** When `antagonist_appearance` is non-empty but the name
   matches *no* shot, log a warning naming the antagonist and the shot count.
   That is a script-generation bug, and this pipeline has already been bitten
   once by a failure that looked like normal behaviour.
3. **Unit tests.** `appears_in` is a pure function; detection across a realistic
   shot list is asserted without any API call.

The alternative that removes the weak link — making shots structured objects
with an explicit `antagonist_present` flag — is rejected. Shots are `list[str]`
throughout the pipeline, and that change would ripple into the video producer,
the stitcher, and every test that constructs a script, for a problem a name
match plus a warning covers.

## 5. Failure handling

| Case | Behaviour |
|---|---|
| No antagonist declared | Today's prompt, byte-identical |
| Name declared, appearance empty | No injection; treated as no antagonist |
| Name shorter than four characters | Never matches; warning fires |
| Name matches no shot | No injection, plus a warning |
| Character-absent shot | No injection, regardless of match |
| Name matches some shots | Inject in those shots only |

Nothing raises. Every degradation lands on current behaviour.

## 6. Verification

Storyboard-only A/B, three samples per arm, ~$0.18 — the method that settled the
locked-appearance question, reusing the same pinned script and reference image.

The success criterion is different and must be stated before the run, not chosen
after seeing the images:

- **Identification:** in each still where both characters appear, can the
  protagonist be identified within two seconds, without reference to the script?
- **Stability:** is the antagonist the same being — palette, silhouette, form —
  across all shots of a sample?
- **Position:** does each character hold their side of frame across the sample?

Scored per still and reported as counts per arm, as in the previous run.

## 7. Scope

| Change | File |
|---|---|
| Two new JSON fields; contrast, naming and blocking rules | `modules/script_generator.py` (prompt) |
| `Antagonist` value object, `appears_in`, injection into both builders | `modules/storyboard.py` |
| Threading through both suppliers | `modules/storyboard.py` |
| Wiring from the script result | `orchestrator.py`, `scripts/manual_episode.py` |

No new API calls, no per-episode cost, no new dependency, no config flag. This
is corrected behaviour for every preset that generates storyboards.
