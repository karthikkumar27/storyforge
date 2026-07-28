import os

# Video provider: "atlas" (default v2), "seedance" (v1), or "kling"
VIDEO_PROVIDER = os.environ.get("VIDEO_PROVIDER", "atlas")

# Image provider: "atlas" (GPT Image 2) or "seedream" (BytePlus)
IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER", "atlas")

# Shared video settings (9:16 vertical, 50s total = 5s title + 40s story + 5s end card).
# Story segment: 5 shots x 8s = 40s, matching the Chronicle of Zenith series bible.
# Title and end card MP4s are auto-prepended/appended when configured per preset
# (assets/title_cards/, assets/end_cards/) — gracefully skipped if assets missing.
SHOT_DURATION = 8
ASPECT_RATIO = "9:16"
SHOTS_COUNT = 5

# Atlas Cloud (unified API — GPT Image 2 + Seedance 1.5 Pro Fast)
ATLAS_BASE_URL = "https://api.atlascloud.ai/api/v1"
ATLAS_VIDEO_MODEL_I2V = "bytedance/seedance-v1.5-pro/image-to-video-fast"
ATLAS_VIDEO_MODEL_T2V = "bytedance/seedance-v1.5-pro/text-to-video"
# Seedance 2.0 — single-clip native-audio video models, used by the
# `single_shot_native` pipeline mode (preset-8 Cinematic Drone). Two variants
# exist; preset config picks one via `seedance2.mode`:
#   t2v: pure text-to-video, full creative freedom on motion (dynamic chases,
#        encounters, human reactions). No image anchoring. Each clip ends
#        mid-action — no loop. Used by preset-8 currently.
#   i2v: image-to-video with `image` (first frame) and optionally `last_image`
#        (last frame). Pass the same image for both to force a natural loop.
#        Kept available for future ambient-loop presets.
# Endpoint: /model/generateVideo. Supports duration 4-15s, ratio 9:16/16:9/etc.
ATLAS_VIDEO_MODEL_SEEDANCE_2_T2V = "bytedance/seedance-2.0/text-to-video"
ATLAS_VIDEO_MODEL_SEEDANCE_2_I2V = "bytedance/seedance-2.0/image-to-video"
# Cheaper alternative for `single_shot_native` presets — Seedance 1.5 Pro Fast t2v.
# ~12x cheaper than Seedance 2.0 (~$0.018/sec vs ~$0.21/sec) but no native audio
# and max duration is 10s (vs 15s for 2.0). Body schema differs slightly:
# uses `aspect_ratio` not `ratio`, plain `720p` not `720p-SR`, no generate_audio.
ATLAS_VIDEO_MODEL_SEEDANCE_1_5_T2V_FAST = "bytedance/seedance-v1.5-pro/text-to-video-fast"
ATLAS_IMAGE_MODEL = "openai/gpt-image-2/text-to-image"
# Image-to-image edit — used to generate per-shot storyboard frames anchored to a
# locked character reference. Each shot calls this with the locked Alan/Zenith URL
# as the base image and the shot's scene description as the prompt, producing a
# new still that keeps the character identical but matches the shot's pose/setting.
ATLAS_IMAGE_EDIT_MODEL = "openai/gpt-image-2/edit"
ATLAS_POLL_INTERVAL_SEC = int(os.environ.get("ATLAS_POLL_INTERVAL_SEC", "15"))
ATLAS_MAX_POLL_ATTEMPTS = int(os.environ.get("ATLAS_MAX_POLL_ATTEMPTS", "60"))

# Kling AI
KLING_BASE_URL = "https://api.klingai.com"
KLING_MODEL = "kling-v1"
KLING_POLL_INTERVAL_SEC = 10
KLING_MAX_POLL_ATTEMPTS = 60

# Seedream (BytePlus ModelArk — image generation)
SEEDREAM_MODEL = "seedream-5-0-260128"

# Seedance (BytePlus ModelArk — video generation)
SEEDANCE_MODEL = "seedance-1-0-pro-250528"
SEEDANCE_BASE_URL = "https://ark.ap-southeast.bytepluses.com/api/v3"
SEEDANCE_RESOLUTION = "720p"
SEEDANCE_POLL_INTERVAL_SEC = 30
SEEDANCE_MAX_POLL_ATTEMPTS = 60

# Base tags applied to EVERY upload (across all presets). Merged with the
# preset/content-specific tags the script generator emits. Reflect the
# underlying generation stack so the channel surfaces in "AI-generated video"
# discovery on YouTube. These live in the HIDDEN tag index — they help SEO
# but are not visible to viewers on the video page.
DEFAULT_TAGS = ["ai", "aivideo", "aigenerated", "seedance", "aishorts"]

# Base hashtags applied to EVERY upload description. Unlike DEFAULT_TAGS,
# these are visible: they appear in the description text, and the first 3
# hashtags in a description render as clickable chips above the title on
# mobile. Use these to signal AI provenance to viewers and boost click-through
# on AI-discovery searches. Merged with each preset's `youtube_hashtags`.
DEFAULT_HASHTAGS = ["ai", "aigenerated", "seedance"]

# Content presets
ACTIVE_PRESET = os.environ.get("CONTENT_PRESET", "preset-1")

PRESETS = {
    "preset-1": {
        "name": "Dark Cinematic",
        "genres": ["sci-fi", "space"],
        "brief_system": (
            "You are a short film story writer for sci-fi and space videos.\n\n"
            "Write a 2-3 sentence story idea for a short video.\n"
            "Make it dark, mysterious, and gripping. One person, one moment, one mystery.\n"
            "Think: Netflix thriller narration."
        ),
        "voice_map": {
            "sci-fi": "pNInz6obpgDQGcFmaJgB",   # Adam — dominant, firm
            "space":  "pNInz6obpgDQGcFmaJgB",   # Adam
        },
        "music_tags": ["cinematic", "dark", "ambient", "atmospheric"],
        "video_style": "photorealistic",
        "story_mode": "series",       # "standalone" or "series"
        "series_parts": 3,
        "youtube_category": "24",     # Entertainment
        "per_shot_storyboards": True,
        # ElevenLabs narration over Seedance native ambient. Photoreal scenes
        # often have busier ambient than anime — keeping ambient slightly lower
        # so dialogue stays intelligible.
        "audio_mix": {
            "mode": "narration_over_native",
            "narration_volume": 1.0,
            "ambient_volume": 0.22,
            "narration_start_offset": 0.0,
        },
    },
    "preset-2": {
        "name": "Shoujo Anime Comedy",
        "genres": ["school-romance", "magical-girl", "slice-of-life", "chibi-chaos"],
        "brief_system": (
            "You are a story writer for short shoujo anime comedy videos.\n\n"
            "Write a 2-3 sentence story idea for a funny, heartwarming short video.\n"
            "Set it in a Japanese high school, magical academy, or cute fantasy world.\n"
            "Include: awkward crushes, over-the-top reactions, sparkly transformations, or silly misunderstandings.\n"
            "The tone is light, bubbly, and wholesome — like a manga panel come to life.\n"
            "Think: funny anime moments that make people smile and share."
        ),
        "voice_map": {
            "school-romance": "cgSgspJ2msm6clMCkdW9",  # Jessica — playful, young
            "magical-girl":   "cgSgspJ2msm6clMCkdW9",  # Jessica
            "slice-of-life":  "cgSgspJ2msm6clMCkdW9",  # Jessica
            "chibi-chaos":    "cgSgspJ2msm6clMCkdW9",  # Jessica
        },
        "music_tags": ["anime", "jpop", "upbeat", "kawaii", "cheerful"],
        "video_style": "anime",
        "story_mode": "standalone",
        "series_parts": 1,
        "youtube_category": "1",      # Film & Animation
        "per_shot_storyboards": True,
        "audio_mix": {
            "mode": "narration_over_native",
            "narration_volume": 1.0,
            "ambient_volume": 0.30,
            "narration_start_offset": 0.0,
        },
    },
    "preset-3": {
        "name": "Fantasy/Mythology",
        "genres": ["fantasy", "mythology", "supernatural", "steampunk"],
        "brief_system": (
            "You are a story writer for short fantasy and mythology videos.\n\n"
            "Write a 2-3 sentence story idea for a short video.\n"
            "Set it in ancient kingdoms, enchanted forests, mythical realms, or steampunk cities.\n"
            "Include: legendary creatures, ancient curses, forbidden magic, or heroic quests.\n"
            "The tone is epic, mysterious, and awe-inspiring — like a myth being told by firelight.\n"
            "Think: Game of Thrones meets Studio Ghibli."
        ),
        "voice_map": {
            "fantasy":      "pNInz6obpgDQGcFmaJgB",  # Adam — dominant, firm
            "mythology":    "pNInz6obpgDQGcFmaJgB",  # Adam
            "supernatural": "pNInz6obpgDQGcFmaJgB",  # Adam
            "steampunk":    "pNInz6obpgDQGcFmaJgB",  # Adam
        },
        "music_tags": ["epic", "orchestral", "fantasy", "mythical", "cinematic"],
        "video_style": "photorealistic fantasy",
        "story_mode": "series",
        "series_parts": 3,
        "youtube_category": "24",     # Entertainment
        "per_shot_storyboards": True,
        "audio_mix": {
            "mode": "narration_over_native",
            "narration_volume": 1.0,
            "ambient_volume": 0.22,
            "narration_start_offset": 0.0,
        },
    },
    "preset-4": {
        "name": "Kids — Toddler Rhymes",
        "genres": ["nursery-rhyme", "counting-song", "animal-song", "lullaby"],
        "brief_system": (
            "You are a children's song writer for toddler rhyme videos.\n\n"
            "Write a 2-3 sentence idea for a short rhyme/song video for toddlers (ages 1-4).\n"
            "The main character is ALWAYS a fluffy orange tabby cat who loves to sing.\n"
            "The cat sings simple, catchy rhymes about colors, animals, numbers, or daily routines.\n"
            "The tone is gentle, repetitive, and joyful — like a nursery rhyme.\n"
            "Keep it VERY simple — toddlers need repetition and bright visuals.\n"
            "Think: Cocomelon meets a singing cat."
        ),
        "voice_map": {
            "nursery-rhyme": "FGY2WhTYpPnrIDTdsKH5",  # Laura — enthusiastic, kids host
            "counting-song": "FGY2WhTYpPnrIDTdsKH5",  # Laura
            "animal-song":   "FGY2WhTYpPnrIDTdsKH5",  # Laura
            "lullaby":       "FGY2WhTYpPnrIDTdsKH5",  # Laura
        },
        "music_tags": ["kids", "nursery", "playful", "cheerful", "gentle", "lullaby"],
        "video_style": "photorealistic",
        "story_mode": "series",
        "series_parts": 999,
        "youtube_category": "10",     # Music
        "extra_skills": ["kids-content-specialist"],
        "made_for_kids": True,        # COPPA — toddler-targeted nursery rhymes
    },
    "preset-5": {
        "name": "Kids — Mini Mart Cat",
        "genres": ["mini-mart-adventure", "customer-chaos", "shelf-stacking", "delivery-day"],
        "brief_system": (
            "You are a story writer for short funny kids videos.\n\n"
            "Write a 2-3 sentence story idea for a short video for kids (ages 3-8).\n"
            "The main character is ALWAYS the SAME realistic orange tabby cat who works at a small mini mart.\n"
            "The cat ALWAYS wears a bright green apron and round glasses (spectacles).\n"
            "The cat runs the mini mart alone — stacking shelves, serving funny animal customers, dealing with silly problems.\n"
            "Each episode is a new mini adventure at the shop — a clumsy delivery, a picky customer, a missing item, a rainy day.\n"
            "The tone is funny, wholesome, and gently educational (counting items, sorting, being polite).\n"
            "Think: a cozy cat shopkeeper having small adventures."
        ),
        "voice_map": {
            "mini-mart-adventure": "N2lVS1w4EtoT3dr4eOWO",  # Callum — husky trickster
            "customer-chaos":     "N2lVS1w4EtoT3dr4eOWO",  # Callum
            "shelf-stacking":     "N2lVS1w4EtoT3dr4eOWO",  # Callum
            "delivery-day":       "N2lVS1w4EtoT3dr4eOWO",  # Callum
        },
        "music_tags": ["kids", "playful", "happy", "ukulele", "whimsical"],
        "video_style": "photorealistic",
        "story_mode": "series",
        "series_parts": 999,
        "youtube_category": "24",     # Entertainment
        "extra_skills": ["kids-content-specialist"],
        "made_for_kids": True,        # COPPA — kids shopkeeper-cat content
    },
    "preset-6": {
        "name": "Kids — Croc Academy",
        "genres": ["science-lesson", "math-fun", "nature-explore", "history-adventure"],
        "brief_system": (
            "You are a writer for short animated educational videos for kids.\n\n"
            "Write a 2-3 sentence idea for a short educational video for kids (ages 4-8).\n"
            "The main character is ALWAYS a friendly green crocodile named Crunchy who teaches kids cool things.\n"
            "Crunchy wears a tiny red bowtie and carries a small chalkboard.\n"
            "Each episode teaches ONE simple concept: why the sky is blue, how to count to 10, what dinosaurs ate, where rain comes from.\n"
            "Crunchy explains things with fun examples, silly comparisons, and asks the viewer questions.\n"
            "The tone is fun, curious, and encouraging — never boring or preachy.\n"
            "Think: animated Bill Nye for preschoolers, but he's a crocodile."
        ),
        "voice_map": {
            "science-lesson":    "TX3LPaxmHKxFdv7VOQHJ",  # Liam — energetic, sharp
            "math-fun":          "TX3LPaxmHKxFdv7VOQHJ",  # Liam
            "nature-explore":    "TX3LPaxmHKxFdv7VOQHJ",  # Liam
            "history-adventure": "TX3LPaxmHKxFdv7VOQHJ",  # Liam
        },
        "music_tags": ["kids", "educational", "upbeat", "cartoon", "fun", "curious"],
        "video_style": "colorful 3D animated cartoon",
        "story_mode": "series",
        "series_parts": 999,
        "youtube_category": "27",     # Education
        "extra_skills": ["kids-content-specialist"],
        "made_for_kids": True,        # COPPA — kids educational content
    },
    "preset-7": {
        "name": "Zenith Chronicles",
        "genres": ["origin-story", "transformation", "galaxy-quest", "earth-encounter"],
        "brief_system": (
            "You are a story writer for short sci-fi anime videos about Zenith.\n\n"
            "Write a 2-3 sentence story idea for a short video.\n"
            "The main character is ALWAYS Alan, aka Zenith — a space traveller whose entire species went extinct when he was young.\n"
            "As he grew up alone, he discovered his hidden powers and abilities.\n"
            "Now he travels the galaxy searching for answers about his race.\n"
            "He found a clue: Voyager-1's golden disk revealed Earth's exact location, and signals suggest a species similar to his own may exist there.\n"
            "Each episode explores the next chapter: Does he find others like him? Will he protect Earth or become its greatest threat? What secrets does his race hold?\n"
            "Show both his normal form and his powerful transformation form (Zenith mode — glowing energy aura, eyes blazing).\n"
            "The tone is epic, emotional, and mysterious — a lone survivor searching for belonging.\n"
            "IMPORTANT: Do NOT use any copyrighted character names or franchise references.\n"
            "Think: last survivor of an alien race discovers Earth and must choose his destiny."
        ),
        "voice_map": {
            "origin-story":      "pNInz6obpgDQGcFmaJgB",  # Adam — dominant, intense
            "transformation":    "pNInz6obpgDQGcFmaJgB",  # Adam
            "galaxy-quest":      "pNInz6obpgDQGcFmaJgB",  # Adam
            "earth-encounter":   "pNInz6obpgDQGcFmaJgB",  # Adam
        },
        "music_tags": ["epic", "sci-fi", "emotional", "orchestral", "cosmic", "mysterious"],
        "video_style": "anime cel-shaded, cinematic sci-fi",
        "story_mode": "series",
        "series_parts": 999,
        "youtube_category": "1",      # Film & Animation
        "per_shot_storyboards": True,
        # --- capabilities (see modules/preset.py) ---------------------------
        # These replace the `ACTIVE_PRESET == "preset-7"` checks that used to
        # be scattered across seven files. A new serialized preset declares
        # them here rather than adding another identity check in code.
        "extra_skills": ["chronicle-of-zenith-canon"],
        # Arc context + locked character roster + character_form selection.
        "serialized_canon": True,
        # Absolute Episode Numbers across the whole 200-episode run.
        "tracks_episode_numbers": True,
        # Published title format. {episode_number} and {title} are filled in.
        "youtube_title_template": "The Chronicle of Zenith — Ep {episode_number}: {title}",
        # Dedicated episode sheet, separate from the main GOOGLE_SHEET_ID.
        "episode_sheet_env": "ALAN_STORY_GOOGLE_SHEET_ID",
        # Hashtags prepended to the YouTube description for discoverability.
        # First 3 also become clickable above the title on mobile.
        # Order matters — most specific/relevant first.
        "youtube_hashtags": ["anime", "fantasy", "japan", "korea", "shorts"],
        # Title / end cards — drop PNG + MP3 files at these paths; pipeline auto-builds MP4.
        # If files are missing, cards are silently skipped (current behavior preserved).
        "title_card": {
            "image": "assets/title_cards/zenith.png",
            "audio": "assets/title_cards/zenith_sting.mp3",
            "duration": 2.0,
            "fade_in": 0.3,
            "fade_out": 0.2,
        },
        # Override narration window — start at 3.0s (1s after title card ends,
        # so there's a beat before Adam speaks). Without this override, the
        # narration would start at 2.0s (right when the title card ends).
        # End buffer auto-derives from end_card.duration below.
        "end_card": {
            "image": "assets/end_cards/zenith.png",
            "audio": "assets/end_cards/zenith_sting.mp3",
            "duration": 5.0,
            "fade_in": 0.3,
            "fade_out": 0.8,
        },
        # Audio mix — narration over native (Seedance ambient + SFX) audio.
        # Setting "mode": "narration_over_native" tells the orchestrator to use
        # AudioMixer.mix_with_native_audio() instead of skipping ElevenLabs entirely.
        # Volumes follow broadcast voiceover convention: narration ~1.0, ambient
        # bed at ~0.30-0.35 — audible but doesn't fight the voice.
        "audio_mix": {
            "mode": "narration_over_native",
            "narration_volume": 1.0,
            "ambient_volume": 0.32,
            # Narration starts at 3.0s — 1.0s breathing room after the 2.0s title card,
            # then Adam begins. End offset still auto-derives from end_card.duration.
            "narration_start_offset": 3.0,
        },
    },
    "preset-8": {
        "name": "Cinematic Drone",
        # Each genre is a SCENARIO TYPE the brief generator picks randomly
        # per video. The brief_system below has a dedicated archetype for each
        # — Claude pulls the right one based on which subject got chosen.
        "genres": [
            "urban-chase", "wildlife-encounter", "impossible-vista", "human-reaction",
            "landscape-sweep", "coastal-flight",
        ],
        "brief_system": (
            "You are a video prompt writer for cinematic 9:16 first-person aerial-POV\n"
            "drone Shorts. Each video is ONE 12-second cinematic moment — not ambient\n"
            "footage. Every clip must make a viewer say \"wait, what?\" and rewatch.\n\n"
            "============================================================\n"
            "POV REQUIREMENT (CRITICAL):\n"
            "============================================================\n"
            "The camera IS the drone. First-person aerial view shot FROM the drone,\n"
            "NOT a video OF a drone. The drone itself MUST NOT appear in the frame —\n"
            "no propellers, no chassis, no shadow of a drone on the ground.\n"
            "USE phrases: 'aerial view glides over...', 'the camera dives toward...',\n"
            "'racing past...', 'looking down at...', 'sweeping through...'.\n"
            "AVOID: 'a drone hovers', 'a drone flies', 'a quadcopter circles' —\n"
            "those describe a third-person shot of a drone, which is wrong.\n\n"
            "============================================================\n"
            "SCENARIO ARCHETYPES — your user prompt assigns ONE. Write FOR that one:\n"
            "============================================================\n\n"
            "URBAN-CHASE:\n"
            "The camera follows a moving subject through city streets — sprinting parkour\n"
            "runner, racing cyclist, weaving motorcyclist, fleeing car, kid on a scooter.\n"
            "The camera weaves between buildings, dips under fire escapes, swoops past\n"
            "awnings and laundry lines. Pedestrians on sidewalks look up startled as the\n"
            "camera whooshes past low. End mid-chase — never on a resolution. Pick a\n"
            "specific city (Tokyo backstreets, Marrakech medina, Mumbai market, Lisbon\n"
            "alleys, São Paulo favela). Audio: rushing wind, footsteps on pavement, city\n"
            "ambient, surprised gasps and shouts in the local language.\n\n"
            "WILDLIFE-ENCOUNTER:\n"
            "The camera glides silently through a wild environment and captures a moment\n"
            "normal photography cannot — a stag stepping into a misty clearing and looking\n"
            "up, wolves crossing a frozen river single-file, a humpback whale breaching\n"
            "directly beneath the camera, an eagle launching from its perch at eye level,\n"
            "a snow leopard padding across a ridge. The animal sees the camera and reacts.\n"
            "End mid-encounter. Audio: ambient nature + the animal's specific sound\n"
            "(hooves on twigs, whale spray, wing beats, paws on stone).\n\n"
            "IMPOSSIBLE-VISTA:\n"
            "The camera flies through a geography photography normally cannot reach:\n"
            "between two waterfalls cascading into a chasm, under a stone arch then up a\n"
            "cliff face, through a cherry-blossom canopy with petals raining past, into\n"
            "and out of a sea cave, along the edge of a volcanic crater rim, threading\n"
            "between sequoia trunks. No subjects — pure scale, pure awe, pure 'how was\n"
            "this shot.' End on the moment of maximum awe (cresting a cliff, emerging\n"
            "from a cave). Audio: roar of water, wind through stone, crashing waves.\n\n"
            "HUMAN-REACTION:\n"
            "The camera passes low (8-15m altitude) over a gathering of people — busy\n"
            "Marrakech market, beach in Bali, festival in Rio, playground in Tokyo,\n"
            "fishing village in Vietnam, harvest in rural Italy. People look up startled\n"
            "— pointing, laughing, kids chasing on foot, vendors shielding their eyes,\n"
            "elders smiling. The camera doesn't stop, it continues forward as more\n"
            "people notice. End still in motion. Audio: vendor cries, children's\n"
            "laughter, gasps, conversations in the location's native language.\n\n"
            "LANDSCAPE-SWEEP:\n"
            "The camera glides high and wide over expansive natural landscapes — sweeping\n"
            "over rolling Tuscan hills at golden hour, gliding above terraced rice paddies\n"
            "in Bali, racing across the white expanse of Salar de Uyuni, skimming over the\n"
            "rust-red dunes of Wadi Rum, threading through autumn forests in Hokkaido,\n"
            "banking past basalt columns of the Giant's Causeway. No subjects, no chase —\n"
            "scale of the land and the camera's motion through it ARE the subject. End on\n"
            "a moment of revelation (cresting a ridge, banking past a peak, sun breaking\n"
            "through clouds). Audio: wind across the land, distant birds, the rustle of\n"
            "grass or shifting sand.\n\n"
            "COASTAL-FLIGHT:\n"
            "The camera flies low over the interface of water and shore — racing the\n"
            "breaking surf along Portugal's Nazaré cliffs, skimming the turquoise lagoons\n"
            "of Mauritius, dipping into the sea spray of Big Sur, sweeping past the chalk\n"
            "cliffs of Étretat, threading between Australia's Twelve Apostles, banking\n"
            "across the black-sand beaches of Iceland's Reynisfjara. Waves, foam, tide\n"
            "pools, rocky outcrops, headlands. People may dot the beaches below but the\n"
            "camera doesn't stop for them — it continues forward, parallel to the coastline\n"
            "or banking out over open water. End mid-arc, still moving. Audio: rolling\n"
            "surf, gulls, wind off the water, the hiss of foam on sand.\n\n"
            "============================================================\n"
            "UNIVERSAL RULES (apply to all scenarios):\n"
            "============================================================\n"
            "- Single continuous shot. No cuts. No fades to black.\n"
            "- Cinematic energy — every video must have an 'unmissable' hook.\n"
            "- Audio is MANDATORY — always describe specific ambient + subject sounds.\n"
            "  Seedance 2.0 generates audio natively; sound cues you write will be rendered.\n"
            "- 80-140 words. One paragraph. Plain prose. No bullet points.\n"
            "- No camera-tech jargon ('f/2.8', 'ProRes', '4K HDR'). Seedance ignores those.\n"
            "- No narration, no scripted dialogue. People in the scene may shout naturally.\n"
            "- End MID-ACTION. Do NOT resolve. Do NOT cut to black. Do NOT slow to a stop.\n"
            "  The clip ends while the camera is still moving and the moment is still alive."
        ),
        "voice_map": {},   # unused — Seedance 2.0 generates native audio
        "music_tags": [],  # unused
        "video_style": "cinematic first-person aerial drone, dynamic, dramatic",
        "story_mode": "standalone",
        "series_parts": 1,
        "youtube_category": "19",   # Travel & Events
        "youtube_hashtags": ["dronefootage", "cinematic", "fpv", "shorts", "viral"],
        # Marks this preset as bypassing the multi-shot pipeline. Orchestrator
        # uses a simplified flow: brief → Seedance 2.0 t2v → upload. No script
        # gen, no image gen, no per-shot storyboards, no stitcher, no audio mixer,
        # no post-processing (the cinematic shots end mid-action, no loop).
        "pipeline_mode": "single_shot_native",
        "seedance2": {
            "mode": "t2v",            # "t2v" (cinematic action) or "i2v-loop" (ambient loop)
            # model_variant picks the producer + schema. "2.0" uses Seedance 2.0
            # (native audio, $2.56/12s). "1.5-fast" uses Seedance 1.5 Pro Fast
            # (~$0.018/sec, no audio, max 10s) — ~12x cheaper for silent drone
            # cinematic Shorts.
            "model_variant": "1.5-fast",
            "duration": 10,           # 1.5-fast max is 10s; 2.0 supports up to 15s
            "resolution": "720p",     # 1.5-fast: 720p / 1080p. 2.0 adds 720p-SR.
            "ratio": "9:16",
            "generate_audio": True,   # ignored by 1.5-fast (no native audio capability)
            "watermark": False,
        },
    },
}

# Resolve active preset
_preset = PRESETS[ACTIVE_PRESET]
PRESET_NAME = _preset["name"]
GENRES = _preset["genres"]
BRIEF_SYSTEM_CONTEXT = _preset["brief_system"]
VOICE_MAP = _preset["voice_map"]
MUSIC_TAGS = _preset["music_tags"]
VIDEO_STYLE = _preset["video_style"]
STORY_MODE = _preset["story_mode"]
SERIES_PARTS = _preset["series_parts"]
YOUTUBE_CATEGORY_ID = _preset["youtube_category"]

# ElevenLabs
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"

# Claude
CLAUDE_MODEL = "claude-sonnet-4-6"

# YouTube
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
