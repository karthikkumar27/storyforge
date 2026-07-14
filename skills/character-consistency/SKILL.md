---
name: Character Consistency
description: Universal techniques for keeping characters visually consistent across multiple AI-generated shots — locked paragraphs, outfit lock, hero reference frame, two-generation rule. Applies to every preset.
---

# Character Consistency

You are responsible for one of the hardest problems in AI video: **making the same character look like the same character across multiple shots, episodes, or arcs.** AI models drift. This skill defines the discipline that fights drift.

## Why This Skill Exists

By shot 3 of an AI video, faces shift slightly. By episode 30, the protagonist has visibly changed. By episode 100, viewers don't recognize the character anymore. The entire emotional investment collapses. These rules prevent that.

---

## 1. The Locked Character Paragraph — Treat It Like a Contract

For every named character, write **one paragraph** describing their appearance. **Paste it verbatim into every prompt that includes them. Never paraphrase. Never abbreviate.**

**Example for Alan / Zenith (resting form):**

> Alan Vorne (Zenith, resting form): Late 30s appearance, lean build, 5'11". Dark brown hair, slightly overgrown, gray streaks at temples. Pale skin with a faint cool undertone. Eyes deep blue-gray. Wears a dark gray wool coat over a faded black sweater, charcoal trousers, weathered boots. A small silver pendant — a two-pointed star — visible at the collar. Quiet face. Rarely smiles. Holds himself still.

**Example for the Mini Mart Cat:**

> A fluffy orange tabby cat with white chest patch, age unknown but adult, medium-sized. Round amber eyes, alert and friendly. Wears a bright green canvas apron with a small front pocket, and round gold-rimmed glasses perched on his pink nose. Soft pink ears with one slightly darker tip. Tail held upright, almost always.

**Rules:**
- Always include: species/ethnicity, age range, build, hair color/style, eye color, skin tone, distinctive features
- Always include the **default outfit** — this is the consistency cheat that does most of the work
- Use specific colors ("dark navy" not "blue", "weathered brown leather" not "boots")
- The paragraph never changes unless the character has a story-driven appearance shift (transformation, injury, aging)

---

## 2. The Outfit Lock — Your Strongest Consistency Tool

Each character has **one default outfit**. They wear it almost always. Wardrobe changes are **story moments**, not casual variations.

| Character | Default outfit | When it changes |
|-----------|----------------|----------------|
| Alan Vorne | Dark gray coat, black sweater, charcoal trousers | Never in resting form. Veyl form has its own consistent look. |
| Mini Mart Cat | Green apron, round glasses | Only on special episodes (e.g., rainy day = adds a hat) |
| Crunchy the Croc | Tiny red bowtie, small chalkboard | Always. The bowtie is the brand. |
| Toddler Rhyme Cat | (To be locked when designed) | (To be defined) |

**Why this works:** When the prompt says "Alan walks into the boarding house," the AI generates Alan with his default outfit because the prompt re-states it every time. No drift opportunity.

**Rule:** If you ever change a character's outfit without a story reason, you have lost continuity. Don't do it.

---

## 3. The Hero Reference Frame

For each character, designate **one** image as **the** reference. Every close-up shot of that character should ideally be image-to-video starting from that reference (or one of a small set of locked variants).

For our pipeline:
- The first shot uses the hero reference image as `first_frame`
- Subsequent shots are text-to-video, but the prompt re-pastes the locked character paragraph
- This combination anchors visual identity (image) and behavioral identity (text)

For **transformation characters** (Zenith), maintain TWO hero references:
- One for resting form (Alan)
- One for transformed form (Veyl/Zenith)

The script decides which form is needed for the episode and the pipeline picks the matching reference.

---

## 4. The Two-Generation Rule

> **Never use a previously AI-generated frame as the reference for the next generation.**

Drift compounds. If shot 5 is generated using shot 4's last frame as input, and shot 6 uses shot 5's, by shot 10 the character has visibly mutated.

**Always anchor back to:**
- The original GPT Image 2 hero reference, OR
- A locked, hand-curated reference from your visual bible

**Never use as reference:**
- A frame extracted from a Seedance output
- A face the AI generated last episode
- A "close enough" image you grabbed from the web

This rule is invisible when you're starting out and devastating by episode 30.

---

## 5. The Continuity Reset Discipline

For long-running series (preset-7), do a **continuity audit every 20 episodes**:

1. Pull frame grabs of the protagonist from episodes 1, 10, and 20 of that arc
2. Compare side by side
3. If drift is detected, regenerate the hero reference with the locked paragraph
4. Update the visual bible with the new hero reference
5. Re-anchor any future scenes to the new reference

Without this audit, by episode 50 the character has drifted enough that early viewers won't recognize them.

---

## 6. The Visual Style Prefix — Keep It Short

Each shot prompt is prefixed with a `visual_style` block that defines art direction. Keep it under 25 words. **Never put character description in the visual_style block** — that goes in the locked character paragraph instead.

**Bad visual_style (overloaded):**
> "Soft pastel anime art style with warm rose-gold and cream color palette, glowing school afternoon light, cel-shaded with delicate ink outlines and sparkle overlays. Main character: a lanky Japanese high school boy, age 16, with messy black hair..."

**Good visual_style (focused):**
> "Soft pastel anime, rose-gold and cream palette, warm golden afternoon light, cel-shaded with sparkle overlays."

Then the **character paragraph** is included separately in the prompt body. This separation lets the AI render style and character with appropriate weight.

---

## 7. Per-Preset Palette Discipline

Each preset has a **locked palette**. Append it to every shot's visual_style. The palette should never drift mid-episode unless the story explicitly requires it (transformation, dream, flashback).

| Preset | Palette |
|--------|---------|
| Dark Cinematic | Desaturated blues, blacks, with one accent color (red blood, blue light, amber flame) |
| Shoujo Anime Comedy | Soft pastels, rose-gold and cream, sparkle overlays |
| Fantasy/Mythology | Deep golds, forest greens, royal purples, painterly lighting |
| Kids — Toddler Rhymes | Bright primary colors, sunny lighting, soft shapes |
| Kids — Mini Mart Cat | Warm shop lighting, friendly pastels, bright product colors |
| Kids — Croc Academy | Saturated 3D cartoon palette, primary colors, no shadows |
| Zenith Chronicles | Deep navy, bone white, dust gold. Earth = warmer. Space = colder. Veyl form = inverted (golds → blacks, blues → reds) |

---

## 8. Reference Image Strategy by Preset Type

### Standalone presets (kids rhymes, anime comedy)
- Generate a fresh reference image per video using the locked character paragraph
- The character paragraph anchors consistency across the same video's shots
- Slight variation between videos is acceptable for standalones

### Series presets with persistent main character (Zenith, Dark Cinematic series)
- Use a **locked default reference image** (`default_ref_image` in preset config) for the main character
- Same image every episode → maximum consistency
- Only generate a new reference if the story requires a major appearance shift (transformation form, aging)

### Recurring character presets (Mini Mart Cat, Croc Academy, Toddler Cat)
- Use a locked default reference image, same as above
- Each episode is a new adventure but the character is identical

---

## 9. Multi-Character Episodes

When an episode has multiple named characters:

- **Paste each character's locked paragraph in the prompt**
- Anchor characters to consistent screen positions (LEFT, RIGHT, CENTER) across the episode — see screenplay-director skill
- For close-ups, use the hero reference of that specific character
- For wide shots with both, the visual_style + character paragraphs do the work; expect minor drift
- **Do not introduce BRAND-NEW characters in shots 4-6.** A brand-new character (no prior appearance, no locked paragraph) belongs in shot 1-2 with proper establishing. RECURRING characters from the roster (with a locked paragraph) can appear in any shot — just paste their locked paragraph verbatim wherever they appear.

---

## 10. The Failure Modes

| Failure | Cause | Fix |
|---------|-------|-----|
| Face slightly wrong | Character drift across shots | Re-anchor to hero reference |
| Outfit changes between shots | Prompt didn't include outfit | Always paste full character paragraph |
| Two characters merge into one | AI confused identities | Strong screen-position separation + distinct paragraphs |
| Character looks different next episode | Drifted reference | Two-generation rule violated; reset to original ref |
| Background characters keep changing | Not locked | Use the same generic descriptor ("a tall man with white hair", "a small girl") consistently |

---

## 11. The North Star

> **Treat every named character like a brand asset. The paragraph is their style guide. The hero reference is their logo. Never compromise either for a "cooler" shot.**

Consistency is invisible when it works. Drift is the loudest red flag in AI video. The audience may not articulate why episode 30 feels off, but they feel it, and they leave.

This discipline is the difference between a series and a sequence of unrelated videos.
