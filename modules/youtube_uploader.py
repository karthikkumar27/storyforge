import http.client
import json
import os
import random
import socket
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from config import YOUTUBE_CATEGORY_ID, YOUTUBE_SCOPES, DEFAULT_HASHTAGS
from modules.preset import active_preset

_preset = active_preset()


# Per Google's resumable-upload guidance: transient network/HTTP failures
# during chunk upload should be retried with exponential backoff. Without
# this, a single mid-stream connection drop kills the whole upload — and
# we already paid ~$1 of Atlas video gen by the time we get to YouTube.
RETRIABLE_EXCEPTIONS = (
    http.client.NotConnected,
    http.client.IncompleteRead,
    http.client.ImproperConnectionState,
    http.client.CannotSendRequest,
    http.client.CannotSendHeader,
    http.client.ResponseNotReady,
    http.client.BadStatusLine,
    http.client.RemoteDisconnected,
    ConnectionError,        # includes ConnectionResetError, BrokenPipeError, ConnectionAbortedError
    socket.timeout,
    socket.error,
    OSError,                # broad catch for transport-level I/O issues
)
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_CHUNK_RETRIES = 5


def _build_description(script_description: str) -> str:
    """Prepend hashtags to the description so they appear above the title
    (first 3 on mobile) and boost discoverability.

    Two hashtag sources are merged: the preset-specific list
    (`youtube_hashtags`) FIRST so preset-relevant terms get the clickable
    above-title positions, and the universal `DEFAULT_HASHTAGS` (AI provenance)
    AFTER. YouTube allows up to 15 hashtags in a description; we prefix with
    `#` if missing and de-duplicate case-insensitively.
    """
    preset_hashtags = list(_preset.youtube_hashtags)
    all_hashtags = list(preset_hashtags) + list(DEFAULT_HASHTAGS)
    if not all_hashtags:
        return script_description

    formatted = []
    seen = set()
    for tag in all_hashtags:
        clean = tag.strip().lstrip("#").lower()
        if clean and clean not in seen:
            seen.add(clean)
            formatted.append(f"#{clean}")

    return f"{' '.join(formatted)}\n\n{script_description}"


class YouTubeUploader:
    def __init__(self):
        token_data = json.loads(os.environ["YOUTUBE_OAUTH_TOKEN"])
        self.creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            scopes=YOUTUBE_SCOPES,
        )
        if not self.creds.valid:
            self.creds.refresh(Request())
        self.youtube = build("youtube", "v3", credentials=self.creds)

    def upload(self, video_path: str, script_result: dict) -> str:
        # COPPA: every upload must declare audience. Kids presets (4/5/6) opt
        # in via `made_for_kids: True` in their config block; everything else
        # defaults to False. Setting this explicitly (rather than omitting it)
        # avoids the "pending audience declaration" Studio state that blocks
        # end screens, cards, and other engagement features.
        made_for_kids = _preset.made_for_kids
        audience_label = "MADE FOR KIDS" if made_for_kids else "Not made for kids"
        print(f"[YT] Audience declaration: {audience_label}", flush=True)

        body = {
            "snippet": {
                "title": script_result["title"],
                "description": _build_description(script_result["description"]),
                "tags": script_result["tags"],
                "categoryId": YOUTUBE_CATEGORY_ID,
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": made_for_kids,
            },
        }
        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
        request = self.youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )
        response = None
        MAX_UPLOAD_CHUNKS = 10_000
        chunk_iter = 0

        while response is None:
            chunk_iter += 1
            if chunk_iter > MAX_UPLOAD_CHUNKS:
                raise RuntimeError("YouTube upload did not complete after maximum chunk iterations")

            # Retry the SAME chunk on transient errors. Resumable uploads let
            # us call next_chunk() again to resume from the last acknowledged
            # offset, so we don't lose progress on a network blip.
            chunk_retry = 0
            while True:
                try:
                    _, response = request.next_chunk()
                    break  # chunk succeeded — outer loop will fetch the next one (or finish)
                except HttpError as exc:
                    status = exc.resp.status if exc.resp else 0
                    if status in RETRIABLE_STATUS_CODES and chunk_retry < MAX_CHUNK_RETRIES:
                        chunk_retry += 1
                        backoff = (2 ** chunk_retry) + random.random()
                        print(f"[YT] HTTP {status} on chunk — retry {chunk_retry}/{MAX_CHUNK_RETRIES} in {backoff:.1f}s", flush=True)
                        time.sleep(backoff)
                        continue
                    raise
                except RETRIABLE_EXCEPTIONS as exc:
                    if chunk_retry < MAX_CHUNK_RETRIES:
                        chunk_retry += 1
                        backoff = (2 ** chunk_retry) + random.random()
                        print(f"[YT] Transient error ({type(exc).__name__}: {exc}) — retry {chunk_retry}/{MAX_CHUNK_RETRIES} in {backoff:.1f}s", flush=True)
                        time.sleep(backoff)
                        continue
                    raise

        return f"https://www.youtube.com/watch?v={response['id']}"
