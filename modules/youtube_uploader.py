import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from config import YOUTUBE_CATEGORY_ID, YOUTUBE_SCOPES


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
        body = {
            "snippet": {
                "title": script_result["title"],
                "description": script_result["description"],
                "tags": script_result["tags"],
                "categoryId": YOUTUBE_CATEGORY_ID,
            },
            "status": {"privacyStatus": "public"},
        }
        media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
        request = self.youtube.videos().insert(
            part="snippet,status", body=body, media_body=media
        )
        response = None
        MAX_UPLOAD_CHUNKS = 10_000
        for _ in range(MAX_UPLOAD_CHUNKS):
            _, response = request.next_chunk()
            if response is not None:
                break
        else:
            raise RuntimeError("YouTube upload did not complete after maximum chunk iterations")
        return f"https://www.youtube.com/watch?v={response['id']}"
