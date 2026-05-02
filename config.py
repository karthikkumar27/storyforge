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
        # Title / end cards — drop PNG + MP3 files at these paths; pipeline auto-builds MP4.
        # If files are missing, cards are silently skipped (current behavior preserved).
        "title_card": {
            "image": "assets/title_cards/zenith.png",
            "audio": "assets/title_cards/zenith_sting.mp3",
            "duration": 5.0,
            "fade_in": 0.5,
            "fade_out": 0.3,
        },
        "end_card": {
            "image": "assets/end_cards/zenith.png",
            "audio": "assets/end_cards/zenith_sting.mp3",
            "duration": 5.0,
            "fade_in": 0.3,
            "fade_out": 0.8,
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
