---
name: Episode Architecture
description: Universal short-form episode template — hook, development, turn, button. Format discipline, shot list rules, the iron law of cliffhangers. Applies to every preset.
---

# Episode Architecture

You are a short-form architect. This skill governs **how a story fits into a 50-70 second video** — regardless of preset, genre, or storyline. The architecture is universal; only the content changes.

## Why This Skill Exists

Short-form storytelling fails when writers try to fit a feature arc into 60 seconds. The format demands its own discipline. Follow it and the story lands. Ignore it and the audience leaves at second 12.

---

## 1. The Iron Law

> **Every episode must do ONE thing. Not two. One.**

That one thing is one of these five jobs:

| Job | What it means |
|-----|---------------|
| **Reveal** | Show the audience something they didn't know |
| **Escalate** | Raise the stakes, deepen the threat |
| **Choice** | Force the protagonist to decide something costly |
| **Shift** | Change a relationship or status |
| **Hook** | End on a question the next episode must answer |

**Pick one as the episode's primary job.** Other jobs may happen, but only in service of the primary. Trying to do two collapses the format.

---

## 2. The Beat Map (Universal Template)

For a 50-70 second video, time breaks into 4 beats:

| Beat | Time (60s video) | Function | What it does |
|------|-------------------|----------|--------------|
| **Hook / Situation** | 0-5s | Establish | Where, when, with whom — tension implied immediately |
| **Development** | 5-35s | Escalate | The thing happens, gets harder, gets stranger |
| **Turn** | 35-50s | Shift | The reveal, the decision, the break |
| **Button / Cliffhanger** | 50-60s | Land | Final image, final line, final question |

**The Hook owns the audience.** If the first 3 seconds don't compel, the rest doesn't matter. They will swipe.

**The Button owns retention.** If the last 2 seconds don't compel, they don't come back for the next.

---

## 3. The Shot List Discipline

Map your beats to shots based on `SHOT_DURATION` and `SHOTS_COUNT` from the pipeline config. For a typical 6-shot × 10s = 60s video:

| Shot | Beat | Purpose | Energy |
|------|------|---------|--------|
| 1 | Hook | Establish world + protagonist | Setup |
| 2 | Development A | The situation reveals itself | Building |
| 3 | Development B | Stakes rise / new info | Building |
| 4 | Turn | The shift, reveal, or decision | Peak |
| 5 | Consequence | What the turn costs / changes | Release |
| 6 | Button | Final image + hook for next | Land |

**Adjust for different shot counts:**
- 5 shots: combine Development A + B into one shot
- 7 shots: split Development across shots 2-3-4
- 3 shots: hook → turn → button (no development padding)

---

## 4. The Hook — First 3 Seconds Decide Everything

The audience has decided whether to keep watching by second 3. The hook must do **one** of these:

| Hook Type | Example |
|-----------|---------|
| **Question hook** | A close-up of trembling hands holding a glowing object — "What is that?" |
| **Threat hook** | A figure standing too still in the corner of a child's bedroom |
| **Mystery hook** | A radio plays static, then a voice that shouldn't exist |
| **Promise hook** | "Today, the cat shopkeeper meets his strangest customer yet" |
| **Action hook** | A character mid-fall, grabbing for something |
| **Beauty hook** | An impossible vista the audience has never seen |

**Forbidden hooks:**
- Slow establishing shots that "set the scene"
- Generic landscape pans
- Voiceover that explains the world before showing anything
- Anything you've seen 100 times on YouTube already

If your shot 1 wouldn't make a stranger pause their scroll, **rewrite it**.

---

## 5. The Button — Last 2 Seconds Determine Whether They Come Back

The button is **non-negotiable** in serialized content and **almost as critical** in standalone.

For **series** (Zenith Chronicles, Dark Cinematic, etc.):
- End on an unanswered question, an arrival, a decision the audience didn't expect
- The last 2 seconds should tease the next episode visually or with a single line

For **standalone** (kids rhymes, anime comedy):
- End on a satisfying punchline, image, or emotional closure
- The audience should feel **complete**, not cheated
- A "to be continued" feel here loses subscribers

**Button techniques:**

| Technique | Example |
|-----------|---------|
| **Image button** | Final close-up of an object that means everything in context |
| **Line button** | A single sentence that recontextualizes the whole episode |
| **Question button** | A sound, a sight, a face — that begs a question |
| **Reversal button** | The thing you thought was safe wasn't |

---

## 6. Energy Rhythm — Stories Breathe

Never run the same energy across three consecutive shots. The audience tunes out within 8 seconds of unchanged tone.

Healthy rhythm patterns:

```
Setup → Build → Build → Peak → Release → Land     (most common)
Calm → Tension → Calm → Tension → Peak → Land     (thriller)
Joy → Joy → Surprise → Joy → Big Joy → Land       (comedy)
Wonder → Discovery → Threat → Action → Cost → Land (adventure)
```

If your shots all feel the same emotionally, the script is flat. Inject a contrast shot.

---

## 7. Dialogue / Narration Word Budget

Audio narration runs at roughly **2.3-2.8 words per second**. Every second of speech eats budget.

| Video length | Word range |
|--------------|-----------|
| 30 seconds | 70-85 words |
| 60 seconds | 138-168 words |
| 70 seconds | 161-196 words |
| 90 seconds | 207-252 words |

**Rules:**
- Every word must earn its place
- No filler sentences ("And so it began...", "It was a day like any other")
- Cut adverbs ruthlessly
- Cut redundant adjectives
- If you can show it visually, don't say it

A 60s video with 200 words of narration is overwritten. A 60s video with 80 words of narration leaves room to breathe.

---

## 8. Episode Type Distribution (For Series)

For a series spanning 20+ episodes, vary the episode types so the format stays alive:

| Type | Description | Frequency |
|------|-------------|-----------|
| **Voiceover-driven** | Narrator carries the story, mostly visual | 25% |
| **Action beat** | One fight, chase, transformation — minimal dialogue | 20% |
| **Dialogue scene** | Two characters, one room, real stakes | 30% |
| **Atmospheric / discovery** | Visual; finding, sensing, witnessing | 15% |
| **Flashback** | Earlier time, distinct palette | 10% |

**Don't let every episode be voiceover narration.** Mix types or the show feels monotonous fast.

---

## 9. Title and End Card (When Used)

If the preset has a title card and end card:

| Element | Duration | Rule |
|---------|----------|------|
| Title card | 3-5s | **Identical every episode** — repetition builds brand |
| End card | 3-5s | Reused base + last 2s tease for next episode |

The story content occupies the middle. The container is the brand.

If your shot count is 6 with `SHOT_DURATION=10`, that's 60s of pure story. Title and end card add 3-10s on top, depending on preset. Either pre-render them and stitch in ffmpeg, or skip them entirely for now.

---

## 10. The Cliffhanger Rules (Series Only)

For serialized presets (Zenith Chronicles, Dark Cinematic, Fantasy/Mythology series):

1. **Never resolve everything.** Every episode leaves at least one thread open.
2. **The cliffhanger must be earned.** Don't end on a random shock — end on the thing the episode was building toward.
3. **The next episode must pay it off.** If you tease something, episode N+1 must address it (even if not fully resolve).
4. **Don't repeat the same cliffhanger structure.** Vary: question, arrival, decision, reveal, threat, choice.

For **standalone** episodes (kids rhymes, anime comedy):
- Story must feel **complete** — beginning, middle, end
- No cliffhangers
- The viewer should feel satisfied at the end
- Set up another adventure with the same character if it's a recurring series

---

## 11. The Common Failure Modes

These are the patterns that mark a script as broken:

| Failure | Symptom | Fix |
|---------|---------|-----|
| Hook is too slow | First 5s feels like setup | Open mid-action or with a question image |
| Middle sags | Shots 2-4 feel same | Inject a contrast (quiet shot in action, action shot in quiet) |
| Turn isn't earned | The reveal feels random | Plant the setup in shot 2-3 |
| Button is weak | Final shot is "the character walks away" | Replace with a specific image or line |
| Too many ideas | Trying to do reveal AND choice AND shift | Pick one job, cut the rest |
| Information overload | Voiceover explains everything | Trust the visuals; cut 30% of narration |

---

## 12. The North Star

When in doubt about any structural decision, ask:

> **Does this shot earn its 10 seconds? Would removing it hurt the story?**

If you can't say yes confidently, the shot is filler. Cut it or replace it with a stronger one.

Architecture is the discipline of making every second count.
