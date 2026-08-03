# Alan Story Sheets — Schema Reference

Preset-7 (Chronicle of Zenith) uses **two dedicated Google Sheets**, separate
from the main `GOOGLE_SHEET_ID` used by all other presets. Schema lives here
so you can rebuild or extend the sheets confidently.

---

## Sheet 1 — Episodes (`ALAN_STORY_GOOGLE_SHEET_ID`)

This is preset-7's equivalent of the main sheet — one row per Zenith episode.
It should match the headers of the main sheet so `GSheetReader` works against
it without code changes.

### Required columns

| Column | Type | Filled by | Purpose |
|--------|------|-----------|---------|
| `title` | string | brief generator | Episode title (3-5 words) |
| `story_brief` | string | brief generator | 2-3 sentence story idea |
| `script_text` | string | script generator | Full voiceover narration |
| `ref_image_url` | URL | image generator / preset default | First-frame reference image |
| `genre` | string | brief generator | One of preset-7's genres |
| `series_id` | string | brief generator | Stable ID for the entire Zenith run |
| `part_number` | int | brief generator | Same as episode_number for preset-7 |
| `story_mode` | string | brief generator | Always `series` for preset-7 |
| `duration_sec` | int | append_pending_row | Total episode duration (default 75) |
| `status` | string | pipeline | `pending` → `generating` → `uploading` → `done` (or `error`/`skipped`) |
| `youtube_url` | URL | YouTube uploader | Final published URL |
| `error_msg` | string | pipeline (on failure) | Last error |
| `arc_number` | int | pipeline (auto-added) | 1-10, derived from episode_number |
| `episode_number` | int | pipeline (auto-added) | Absolute episode number 1-200 |
| `character_appearance` | string | pipeline (auto-added) | The prompt that generated `ref_image_url`, saved alongside it so a rerun reads the words that actually match the image rather than a freshly regenerated one |

### Pasteable header row (CSV)

```
title,story_brief,script_text,ref_image_url,genre,series_id,part_number,story_mode,duration_sec,status,youtube_url,error_msg,arc_number,episode_number,character_appearance
```

### Auto-added columns

`arc_number`, `episode_number`, `character_form`, and `character_appearance`
are added automatically by `ensure_columns()` — on `record()` as well as when
a new episode row is appended — the first time the pipeline runs against the
sheet. You don't need to add them by hand.

---

## Sheet 2 — Characters (`ALAN_STORY_CHARACTERS_GOOGLE_SHEET_ID`)

A roster of every named character in The Chronicle of Zenith. The pipeline reads
this on every preset-7 episode brief to inject the relevant characters'
**locked appearance paragraphs** into Claude's context. This is what fights
character drift across 200 episodes.

### Required columns

| Column | Type | Purpose |
|--------|------|---------|
| `character_name` | string | Canonical name (e.g. "Alan Vorne") |
| `alias` | string | Alternate name(s) — e.g. "Zenith", "Zen-Aithar" |
| `role` | string | `main` / `villain` / `ally` / `mentor` / `mystery` |
| `relation_to_main` | string | `self` / `enemy` / `mentor` / `lover` / `rival` / `unknown` |
| `appearance_normal` | string | **LOCKED** appearance paragraph — pasted verbatim into prompts |
| `appearance_transformed` | string | LOCKED transformed-form description (if applicable, else blank) |
| `ref_image_normal` | URL | Reference image for resting form (used as image-to-video first frame) |
| `ref_image_transformed` | URL | Reference image for transformed form |
| `backstory` | string | 1-3 sentence backstory snippet |
| `first_episode` | int | Episode number where the character first appears |
| `status` | string | `active` / `dead` / `missing` / `unknown` |

### Optional columns (used if present, ignored otherwise)

| Column | Type | Purpose |
|--------|------|---------|
| `arcs_active` | string | Comma-separated arc numbers, e.g. `"1,5,8"`. If set, overrides the first_episode + status fallback for arc filtering. |
| `last_episode_appeared` | int | Auto-updated by pipeline (Phase 5+) |

### Pasteable header row (CSV)

```
character_name,alias,role,relation_to_main,appearance_normal,appearance_transformed,ref_image_normal,ref_image_transformed,backstory,first_episode,status,arcs_active,last_episode_appeared
```

### Seed row (Alan / Zenith)

Recommended values to drop in immediately:

```
Alan Vorne,Zenith,main,self,"Late 30s appearance, lean build, 5'11\". Dark brown hair slightly overgrown, gray streaks at temples. Pale skin with a faint cool undertone. Eyes deep blue-gray. Wears a dark gray wool coat over a faded black sweater, charcoal trousers, weathered boots. A small silver pendant — a two-pointed star — visible at the collar. Quiet face. Rarely smiles. Holds himself still.","Larger than Alan, 6'4\", hairless. A crystalline second skin plates his torso, shoulders, and forearms in pale-gold-and-bone fragments. Two-pointed stars of light glow where eyes should be. No clothing in this form. The same pendant visible, glowing faintly. Movement is slower than human, weighty.",,,Last survivor of the Aevari race. Hidden by his mother in a sleep-pod as Sael was destroyed. 217 years old. Decoded Voyager-1's golden disk and set course for Earth.,1,active,"1,2,3,4,5,6,7,8,9,10",
```

### How arcs_active filters work

For each episode, the pipeline:

1. Resolves `arc_number` from the episode_number (e.g. ep 23 → arc 2)
2. Calls `CharactersReader.get_active_for_arc(2)` 
3. For each character row:
   - If `arcs_active` is filled: include if `2` is in the list
   - Else: include if `first_episode` falls in or before arc 2 AND `status` is `active`
4. Pastes each included character's locked paragraphs into the brief generator prompt

This means you can:
- Use `arcs_active` for precise arc-by-arc control (recommended for major characters)
- Leave it blank for minor characters and let the fallback handle them
- Set `status` to `dead` to remove a character from future episodes (e.g. Sheriff Beaumont after arc 4)

---

## Where the canon roster maps to the sheet

The full character roster lives in
`skills/chronicle-of-zenith-canon/SKILL.md` — that's the locked design intent.
The sheet is the **runtime** version: Claude reads the sheet on each generation,
not the SKILL.md, so changes you make in the sheet take effect on the next run
without any code change.

For a 100-episode-vs-200-episode decision, the canon SKILL.md tags some
characters as essential vs. cuttable. When you populate the sheet, prioritise:

**Essential (cannot cut):** Alan/Zenith, Mira, Veth-Ka, Aithra, Sable, Halden, The Speaker

**Important (cut weakens series):** Edith, Theo, Nana Adaeze, Veth-Sael, Joaquin

**Sacrificeable:** Marco, Helen Avila, Sheriff Beaumont, Dr. Calder, Petra Vance, Lina Voss, Veth-Ord, The Archivist

You can populate the sheet incrementally as each character's first arc approaches.

---

## When to update the characters sheet

| Trigger | Action |
|---------|--------|
| New character introduced this arc | Add a row before generating the episode that introduces them |
| Character's appearance changes (transformation, aging, injury) | Update `appearance_normal` or `appearance_transformed` to reflect new look |
| Character dies | Set `status` to `dead` |
| Character is removed from active arcs | Remove arc from `arcs_active` list |
| New reference image generated | Update `ref_image_normal` / `ref_image_transformed` URL |

---

## What the pipeline does NOT do (yet)

- **Auto-update `last_episode_appeared`** — manual for now, Phase 5+ will automate
- **Auto-pick the right reference image (resting vs transformed)** based on episode content — Phase 5+
- **Backfill characters from existing episode descriptions** — manual for now

These are deliberate gaps — Phase 4 keeps scope tight to: routing + character context injection.
