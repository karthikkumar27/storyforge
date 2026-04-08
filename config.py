# Kling AI
KLING_BASE_URL = "https://api.klingai.com"
KLING_MODEL = "kling-v1"
SHOT_DURATION = "10"
ASPECT_RATIO = "16:9"
SHOTS_COUNT = 7
POLL_INTERVAL_SEC = 10
MAX_POLL_ATTEMPTS = 60

# ElevenLabs voice IDs
ELEVENLABS_BASE_URL = "https://api.elevenlabs.io/v1"
VOICE_MAP = {
    "sci-fi": "pNInz6obpgDQGcFmaJgB",   # Adam
    "horror": "VR6AewLTigWG4xSOukaG",   # Arnold
    "space":  "ErXwobaYiN019PkySvjV",   # Antoni
    "blend":  "ErXwobaYiN019PkySvjV",   # Antoni
}

# Bundled royalty-free music
MUSIC_MAP = {
    "sci-fi": "assets/music/sci-fi.mp3",
    "horror": "assets/music/horror.mp3",
    "space":  "assets/music/space.mp3",
    "blend":  "assets/music/space.mp3",
}

# Claude
CLAUDE_MODEL = "claude-opus-4-6"

# YouTube
YOUTUBE_CATEGORY_ID = "24"   # Entertainment
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
