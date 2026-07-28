# Idea Creator

Turns a story idea into a published YouTube video. This context covers the story
material (what gets made), the production artefacts (what it's made from), and
the ledger (the record of what has been made and what's next).

## Language

### Story

**Preset**:
A named content configuration — genre set, voice, visual style, series rules, and
which sheets and skills apply. The active preset determines everything about what
an Episode looks like.
_Avoid_: channel, profile, mode, config

**Brief**:
The two-to-three sentence story premise for one Episode, written before any visual
decisions exist.
_Avoid_: idea, pitch, synopsis, prompt

**Video Prompt**:
The single paragraph handed directly to the video model for presets that generate
a whole video in one call. Distinct from a Brief: it describes camera, motion and
sound, not story.
_Avoid_: brief, prompt

**Narration**:
The voiceover text spoken over an Episode.
_Avoid_: script, voiceover copy, narrative

**Script**:
The full generated bundle for one Episode — Narration, Shot Prompts, title,
description and tags. A Script contains Narration; it is not Narration.
_Avoid_: screenplay, treatment

**Series**:
A run of Episodes that share continuity. Bounded for some Presets (three parts),
effectively open-ended for others.
_Avoid_: season, show, collection

**Arc**:
A twenty-Episode block of the Chronicle of Zenith, carrying its own dramatic
question, tone and closing beat. Ten Arcs span the two hundred Episodes.
_Avoid_: chapter, act, book

**Episode**:
One published video, and the unit of work the pipeline produces.
_Avoid_: video, entry, item, story

**Episode Number**:
An Episode's absolute position across an entire Series — Ep 1 to Ep 200 for the
Chronicle of Zenith. Assigned once and never reused, because it is published in
the Episode's title.
_Avoid_: index, sequence

**Part Number**:
An Episode's position among the *completed* Episodes of its Series. For bounded
Series this is the meaningful ordinal; it is not interchangeable with Episode
Number, which counts differently when an Episode fails or is skipped.
_Avoid_: episode number, part

**Character Form**:
Which form the main character appears in for an Episode — normal, transformed, or
both. Selects which Reference Image anchors the shots.
_Avoid_: mode, state, variant

**Locked Appearance**:
A character's canonical description, pasted verbatim into generation prompts and
never paraphrased. The mechanism that fights visual drift across a long Series.
_Avoid_: character description, bio

### Production

**Shot Prompt**:
The description of one continuous video clip — action, camera movement and
environment. An Episode is several Shot Prompts in sequence.
_Avoid_: scene, clip description, shot

**Reference Image**:
The locked still that fixes a character's identity. One per character per
Character Form, reused across every Episode they appear in.
_Avoid_: character image, anchor, hero shot

**Storyboard**:
A per-shot still derived from a Reference Image plus a Shot Prompt, used as that
shot's first frame. A Reference Image fixes *who*; a Storyboard fixes *who, where
and in what pose*.
_Avoid_: frame, keyframe, still

**Title Card** / **End Card**:
Fixed-length branded segments prepended and appended to an Episode. Built once per
Preset and reused.
_Avoid_: intro, outro, bumper

### Ledger

**Episode Ledger**:
The authoritative record of every Episode — those published, those in flight, and
the one to work on next. The only thing that knows where a Series has got to.
_Avoid_: sheet, database, tracker, queue

**Claim**:
Taking the next Episode from the Episode Ledger to work on. A Claim either yields
an Episode or reports that none exists and a Brief must be written first.
_Avoid_: fetch, get pending, poll, lock

**Brief Context**:
Everything the brief generator needs when the Episode Ledger has no work to hand
out — prior Briefs to avoid repeating, the Series so far, and the next Episode
Number.
_Avoid_: history, state, metadata

**Run**:
One execution of the pipeline, producing at most one Episode. A Run is the
lifetime of a consistent view of the Episode Ledger: material edited between Runs
is picked up, material edited during a Run is not.
_Avoid_: job, invocation, session, request
