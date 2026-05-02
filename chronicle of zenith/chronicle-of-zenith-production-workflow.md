# THE CHRONICLE OF ZENITH

## Production Workflow — Seedance 1.5 Pro + GPT Image 2

A practical pipeline for producing a 200-episode AI video series. Reflects what each tool can and cannot do as of mid-2026.

---

## 1. The Toolchain at a Glance

| Tool | Purpose | Output | Notes |
|------|---------|--------|-------|
| **GPT Image 2 (ChatGPT Images 2.0)** | Reference frames, storyboards, character sheets | Static images, native 2K, optional 4K | Reasoning-based; supports up to 5 characters / 14 refs with consistency |
| **Seedance 1.5 Pro** | Video clips with synced audio | 4–12s clips, up to 1080p | Image-to-video preserves character; native audio includes lip-sync + ambient sound |
| **ElevenLabs (recommended)** | Locked narrator voice | Audio | Use for Zenith's voiceover to maintain identity across 200 episodes |
| **DaVinci Resolve (free)** | Editing, color, title/end card overlay | Final episode | Free, broadcast-grade; use this rather than a phone editor |
| **A spreadsheet / Notion DB** | Continuity tracking | Reference | Non-negotiable at this scale |

### The key constraint
Seedance generates 4–12 seconds per call. Your 40-second story segment will be **4–8 stitched clips**. Plan every episode as a *shot list*, not a single video.

---

## 2. The Production Pipeline — Bird's Eye

```
[PRE-PRODUCTION] (one-time, ~2–4 weeks)
   │
   ├── Build the Visual Bible (character refs, locations, palette)
   ├── Lock the Title + End Card (made ONCE, reused 200x)
   ├── Lock Zenith's narrator voice (ElevenLabs voice ID)
   └── Set up continuity tracker
        │
        ▼
[PER-EPISODE LOOP] (~4–8 hours per episode once practiced)
   │
   ├── 1. Write 40s script with shot list
   ├── 2. Generate storyboard frames (GPT Image 2) — one per shot
   ├── 3. Generate video clips (Seedance, image-to-video) — one per shot
   ├── 4. Record/generate narration (ElevenLabs)
   ├── 5. Edit clips together in Resolve, layer voice, layer title + end card
   └── 6. Export, log to continuity tracker, publish
```

---

## 3. Pre-Production: The Visual Bible (Do This First)

This is the single most important phase. Skipping it means episode 80 won't look like episode 5, and the audience will leave.

### 3.1 Character Reference Packs

For each of the 21 named characters (see Character Roster), build a **reference pack** in GPT Image 2:

**Per character, generate:**

1. **Front-facing portrait, neutral expression** — the "ID photo"
2. **3/4 angle, neutral expression** — for side-of-face continuity
3. **Profile** — for transformation reveals, dramatic shots
4. **Full body, default outfit** — head to toe, plain background
5. **Hands close-up** — surprisingly important; Zenith's hands recur as a motif
6. **Three "mood" shots** — happy, fearful, in-thought (helps Seedance interpret expression prompts)

**Critical for Zenith specifically:**

- All of the above in **resting form (Alan)**
- All of the above in **Veyl form (transformed)**
- A morph reference — half-transformed
- A "memory loss" reference — same face, slightly hollow eyes, used after transformations

### 3.2 Locking the Character Description

For each character, write a **fixed character paragraph** that you will *paste verbatim* into every Seedance prompt that includes them. Example:

> **Alan Vorne (Zenith, resting form):** Late 30s appearance, lean build, 5'11". Dark brown hair, slightly overgrown, gray streaks at temples. Pale skin with a faint cool undertone. Eyes deep blue-gray. Wears a dark gray wool coat over a faded black sweater, charcoal trousers, weathered boots. A small silver pendant — a two-pointed star — visible at the collar. Quiet face. Rarely smiles. Holds himself still.

This paragraph never changes. Every prompt that uses Alan starts with this paragraph. This is how you fight character drift.

### 3.3 Location Reference Packs

For each major location, generate 4–6 reference frames in GPT Image 2:

- **Wide establishing shot** — exterior, daylight
- **Wide establishing shot** — exterior, night
- **Interior wide**
- **Interior detail** (a corner, a key object)
- **The character's "anchor object"** in the space (Alan's radio, Mira's telescope, Veth-Ka's interface)

Locations to pre-build:

| Location | Episodes | Priority |
|----------|----------|----------|
| Interior of *Last Light* (Zenith's ship) | All arcs | Critical |
| Sael ruins / Sael in flashback | Arcs 1, 5, 8 | Critical |
| Coastal town main street | Arcs 2–4, 9 | Critical |
| Edith Hale's boarding house | Arcs 2–4 | High |
| The observatory (high desert) | Arcs 3–6 | High |
| Halden Cross's compound | Arcs 5–8 | High |
| Council chamber (cosmic, cathedral-scale) | Arcs 7, 9, 10 | Medium |

### 3.4 The Palette Lock

Per the series bible: deep blues, bone whites, dust golds. Earth = warmer; space = colder; transformation = inverted (golds become blacks, blues become reds).

In every Seedance prompt, append a **palette directive**:

> "Color palette: deep navy and bone white, with dust gold accents. Cinematic, slightly desaturated. No vibrant primary colors except in transformation sequences."

---

## 4. The 50-Second Episode — Shot Breakdown

This is the most-used template you'll have. Memorize this structure.

### Standard episode shot list (target: 5 shots × ~8 seconds each)

| Shot | Time in episode | Length | Purpose | Seedance length |
|------|-----------------|--------|---------|------------------|
| **Title card** | 0:00–0:05 | 5s | Identical, reused | Pre-rendered (not Seedance) |
| **Shot 1 — Hook** | 0:05–0:13 | 8s | Establish where/who | 8s clip |
| **Shot 2 — Development** | 0:13–0:21 | 8s | Tension rises | 8s clip |
| **Shot 3 — Development** | 0:21–0:29 | 8s | Beat continues | 8s clip |
| **Shot 4 — Turn** | 0:29–0:37 | 8s | The shift | 8s clip |
| **Shot 5 — Button** | 0:37–0:45 | 8s | The hook for next ep | 8s clip |
| **End card** | 0:45–0:50 | 5s | Reused, with 2s next-ep tease | Pre-rendered |

**Total Seedance generations per episode: 5** (plus the next-ep tease, sometimes a 6th).

You can also do 4×10s clips if your scenes need longer breath, or 8×5s clips for fast-cut action episodes. **Match clip length to scene rhythm — do not default to a fixed length.**

### Why 4–8 clips, not one
Seedance's max is 12 seconds per generation. Even if you went 12s × 4 = 48s, you'd still need to stitch. And shorter clips = more editing control + lower cost per failed regen.

---

## 5. Title and End Card — Build Once, Reuse 200 Times

This is **not** a Seedance task. Build these as final video assets *once* and template them.

### Title card (5s, identical every episode)

Production:

1. Generate 4–6 candidate variations in GPT Image 2 — the two-pointed Aevari star forming from cosmic dust, centered, black field
2. Pick the strongest
3. Animate it in After Effects, DaVinci Resolve Fusion, or Canva (simplest)
4. Add the signature audio sting — a single low tone (one-time recording or generated with ElevenLabs Sound Effects)
5. Export as MP4 master
6. **Drop the same MP4 into every episode timeline. Never regenerate it.**

### End card (5s, with last 2s as next-ep tease)

Slightly more complex:

1. Build the base 3-second end card the same way as the title card (cracked star)
2. The final 2 seconds = **next-ep tease frame** — a single still image generated in GPT Image 2 for that specific episode
3. Template the end card so dropping in a new tease frame takes 30 seconds in your editor

### Why this matters
You will burn out fast if you're generating title and end animations every episode. Lock the brand container, vary only what's inside.

---

## 6. The Per-Episode Workflow (Detailed)

### Step 1 — Write the script (30–60 minutes)

For each episode, write:

- **Logline** — one sentence
- **Job** — which of the 5 episode jobs (reveal / escalate / choice / shift / hook)
- **Shot list** — 5 shots, ~8 seconds each, with:
    - What's in frame
    - Camera move
    - Action
    - Dialogue or VO (with word count — aim for 18–22 words per 8s VO)
- **Final beat** — exact image and exact line for the last 2 seconds

### Step 2 — Storyboard frames (45–90 minutes)

In GPT Image 2, generate **one reference frame per shot** (5–6 frames per episode).

**Prompt template for storyboard frames:**

```
[CHARACTER PARAGRAPH — pasted verbatim from Visual Bible]

[LOCATION PARAGRAPH — pasted from Visual Bible]

Scene: [one-sentence description of action]
Camera: [shot type — close-up / medium / wide / over-shoulder]
Lighting: [key light direction, time of day, mood]
Composition: [where the subject is in frame, what's behind them]
Mood: [single word]

Color palette: deep navy and bone white, with dust gold accents.
Cinematic, slightly desaturated, 35mm film aesthetic.
No text, no watermarks, no logos.
Aspect ratio: 9:16 (vertical for short-form) OR 16:9 (horizontal).
```

**Tip:** Generate each storyboard frame in the *same chat session* in ChatGPT — that's where the 8-frame coherence kicks in and consistency improves.

### Step 3 — Generate video clips (90–180 minutes)

Take each storyboard frame into Seedance 1.5 Pro as the **starting frame** (image-to-video mode).

**Seedance prompt template:**

```
Starting frame: [uploaded GPT Image 2 storyboard frame]

[CHARACTER PARAGRAPH — pasted verbatim again, even though you have a starting frame]

Action: [what happens during the 8 seconds, beat by beat]
Camera move: [push in / pull back / static / pan / handheld / orbit]
Performance: [emotional beat — "he doesn't react / he flinches once / a tear falls"]
Audio: [either "no dialogue, ambient [X]" OR exact line of dialogue]
Pacing: [slow / measured / quickening]
Duration: 8 seconds.
```

**Critical Seedance tips:**

- **Re-paste the character paragraph even when using image-to-video.** The starting frame anchors appearance, but the prompt anchors *behavior and continued consistency*.
- **Be explicit about no dialogue when you don't want any.** Otherwise Seedance may have characters mumble. Say: *"No dialogue. Ambient wind only."*
- **Lock the camera if you want the character to do the moving.** Static cameras give you cleaner results than camera-and-character moving simultaneously.
- **Generate 2–3 takes per shot.** Pick the best. Budget for this.

### Step 4 — Generate the narration separately (30 minutes)

**Don't rely on Seedance for Zenith's voiceover across 200 episodes.** The audio model will subtly drift in tone. Instead:

1. Set up a **single ElevenLabs voice** for Zenith — pick or clone, then never change
2. Per episode, paste the VO script into ElevenLabs, generate, download
3. Use Seedance's generated audio only for **ambient sound and other characters' dialogue**, where slight variation is forgivable

This decouples Zenith's voice from the video model, which is the right call for a 200-episode series.

### Step 5 — Edit (45–90 minutes)

In DaVinci Resolve (or your editor of choice):

1. Drop in the **title MP4** at 0:00
2. Drop in the **5 video clips** in sequence
3. Layer the **ElevenLabs narration** as audio track 2
4. Lower Seedance's native audio to 30–50% where narration plays over it
5. Add the **end card MP4** with the episode-specific tease frame
6. Color-grade for consistency (apply a saved LUT — see §8)
7. Export at 1080p 9:16 (mobile/TikTok/Reels) or 16:9 (YouTube)

### Step 6 — Log everything (10 minutes)

Update your continuity tracker (see §9). Skip this and you will pay for it by episode 30.

---

## 7. Character Consistency — Your Biggest Enemy

At 200 episodes, AI-generated faces will drift. Here's how you fight back:

### Tactic 1 — The Locked Character Paragraph
Already covered. Same paragraph in every prompt, every time. Treat it like a contract.

### Tactic 2 — The Hero Reference Frame
For each character, designate **one** GPT Image 2 portrait as *the* reference. Use it as the starting frame for any close-up Seedance shot of that character. This is the strongest anchor.

### Tactic 3 — The Continuity Reset Episode
Every 20 episodes (i.e., end of each arc), do a **continuity audit**:

- Pull frame grabs of each main character from episodes 1, 10, and 20 of that arc
- Compare side by side
- If drift is detected, regenerate the hero reference and update the visual bible
- Re-anchor any scenes in the next arc to the new reference

### Tactic 4 — The Outfit Lock
Each character has a default outfit (in their character paragraph). They wear it almost always. Wardrobe changes are *story moments*, not casual variations. Edith always wears her cardigan. Mira always has her observatory jacket. Halden always wears the same dark suit. **This is one of the biggest consistency cheats available to you.**

### Tactic 5 — The "Two-Generation" Rule
Never use a Seedance output as a reference for the *next* generation. Always anchor back to a GPT Image 2 frame or the original hero reference. Drift compounds.

---

## 8. Color and Tone Consistency

### The LUT lock
After your first 5–10 finished episodes, build a custom LUT (color grading preset) in DaVinci Resolve that captures your series' look. Apply it to every episode. This unifies inconsistencies that creep in from Seedance.

### The transformation palette flip
When Zenith transforms, the palette inverts. Build **two LUTs** — one for resting state, one for transformed. Toggle in the timeline.

### Time-of-day discipline
Decide, per episode, whether it's day, dusk, night, or "Sael golden" (the warm flashback palette). Don't mix within a single episode unless it's the point.

---

## 9. The Continuity Tracker (Non-Negotiable)

Set up a Notion database or Google Sheet. One row per episode. Columns:

| Column | Example |
|--------|---------|
| Ep # | 023 |
| Arc | 2 — First Contact |
| Logline | Alan fixes Helen's broken radio. |
| Job | Shift |
| Characters present | Alan, Helen Avila, (Veth-Ka VO) |
| Locations | Alan's workshop |
| Outfits | Alan: default. Helen: black mourning dress. |
| Time of day | Late afternoon |
| Continuity callbacks | Helen's husband died in Ep 25 (foreshadow) |
| Setups for later | Helen's pendant — recurs Ep 045 |
| Next-ep tease frame | Alan looking at a sky chart |
| Reference frame IDs used | ALAN_HERO_v1, HELEN_HERO_v1, WORKSHOP_INT_v2 |
| Status | Drafted / Generated / Edited / Published |

Without this, by episode 50 you will not remember what color Halden's car was in episode 38, and the audience will.

---

## 10. Audio Strategy

Seedance generates audio with video. This is great for ambient sound but risky for serialized character voices. Here's how to mix it:

| Audio element | Source | Why |
|---------------|--------|-----|
| Zenith's narration | **ElevenLabs (locked voice)** | 200-episode consistency |
| Other characters' dialogue (≤2 lines per ep) | Seedance native | Acceptable variation |
| Other characters' major monologues (rare) | ElevenLabs (per-character locked voice) | Stakes are high |
| Ambient sound | Seedance native | Synced beautifully |
| Title sting | Pre-recorded | Identical 200x |
| Music score | Optional, per-arc theme | License-free or composed once per arc |

**For minor character dialogue**, pick the ElevenLabs voice during pre-production for at least the top 10 characters and lock them. Your audience will recognize voices subliminally.

---

## 11. Realistic Time and Cost

### Per-episode time (after the first 10)

- Script: 30–60 min
- Storyboard: 45–90 min
- Video generation: 90–180 min (depends on rerolls)
- Narration: 30 min
- Edit: 45–90 min
- Logging: 10 min
- **Total: 4–7 hours per episode**

### Per-episode cost (rough, will vary)

- GPT Image 2 generations: $0.50–$2 (5–10 generations)
- Seedance 1.5 Pro: depends heavily on platform; budget **$3–$10 per episode** for 5 clips at 1080p
- ElevenLabs: $0.20–$0.50 per episode (depending on plan)
- **Total: ~$5–$15 per episode**

### Series total (200 episodes)

- Time: ~1,000–1,400 hours (so realistically 1.5–2 years at part-time pace)
- Cost: ~$1,500–$3,500 in tool fees

This is doable solo, but consider releasing in **batches of 10** rather than burning yourself out trying to publish daily.

### Pacing recommendation
Produce 5 episodes a week, publish 5 a week, never let your bank drop below 20 episodes ahead. The day you run out of buffer is the day quality collapses.

---

## 12. Common Failure Modes (and How to Fight Them)

| Failure | Cause | Fix |
|---------|-------|-----|
| Faces look slightly wrong | Character drift | Re-anchor to hero reference frame |
| Outfits change between shots | Prompt didn't specify outfit | Always include outfit in character paragraph |
| Character does something out-of-character | Seedance hallucinated action | Tighter "Performance:" line; less freedom |
| Lip-sync misses | Seedance native audio used for VO | Use ElevenLabs and mute Seedance dialogue |
| Lighting jumps between shots | No time-of-day discipline | Set time-of-day per episode, enforce in every prompt |
| Episode runs over 50s | Too many shots / too long clips | Cut a shot, or reduce all clips to 7s |
| Episode runs under 50s | Clips came in shorter | Pad with held last frame + ambient sound |
| Background warps | Camera + subject moving simultaneously | Lock the camera unless motion is the point |
| Audience can't tell episodes apart | Too samey visually | Build per-arc location and per-arc lighting variety |
| Burnout at episode 30 | No buffer, no system | The continuity tracker + 20-episode buffer rule |

---

## 13. The First 10 Episodes — A Different Workflow

For episodes 1–10, **do not optimize for speed**. Optimize for *establishing the look*.

- Spend extra time on storyboards
- Generate more takes per shot
- Build out your LUT, your locked voices, your reference frames
- Watch episodes 1–5 back-to-back as a viewer — does Alan look like Alan?

These 10 episodes are also your **portfolio piece**. They prove the show works — to viewers, to potential collaborators, and to yourself.

By episode 10, your per-episode time should drop sharply because the system is built.

---

## 14. Tools — Where to Access Each

- **GPT Image 2 / ChatGPT Images 2.0:** ChatGPT (Plus or Pro plan) for the chat experience; or via API on fal.ai for batch workflows
- **Seedance 1.5 Pro:** Available via Replicate, Runware, fal.ai, or BytePlus directly; check current pricing as it changes
- **ElevenLabs:** elevenlabs.io — Creator plan or higher recommended for series work
- **DaVinci Resolve:** Free download from Blackmagic Design — surprisingly powerful for free
- **Notion / Google Sheets:** Either works for the tracker

---

## 15. The Hard Truth

200 episodes of AI video is genuinely ambitious. A few honest realities:

1. **Quality will vary.** Some episodes will look stunning. Some will look jankier than you want. That's normal. The story carries it.
2. **Consistency is a discipline, not a feature.** No tool gives it to you for free at this scale.
3. **The first 10 will take longer than the next 30 combined** as you build your system.
4. **Plan for tool changes.** Both Seedance and GPT Image are evolving — Seedance 2.0 is already out. By episode 100, you may be on a newer model. Build your character paragraphs and reference packs in a *tool-agnostic* way so you can migrate.
5. **Story is your competitive advantage.** Hundreds of people are making AI video. Almost none have a 200-episode arc with a real series bible. *That* is what will make this work.

---

## 16. Suggested First Steps

This week:

1. Pick the ending (A or B)
2. Generate Zenith's 6-frame reference pack in GPT Image 2 (resting + transformed)
3. Generate the title card frame and have it animated (one-time job)
4. Lock Zenith's narrator voice in ElevenLabs
5. Set up the Notion / Sheets continuity tracker

Next week:

6. Beat-sheet Arc 1 (20 episode loglines)
7. Produce Episode 1 end-to-end as a system test — do not aim for perfection, aim to *find what breaks*
8. Refine based on what broke

By week 4: you're running smoothly and producing 3–5 episodes per week.

---

*Production Workflow v1.0 — Built for Seedance 1.5 Pro + GPT Image 2 as of mid-2026. Revisit when models change.*
