"""One-shot: generate YOUTUBE_OAUTH_TOKEN for .env. Run locally, not on Cloud Run."""
import json
import os

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

from config import YOUTUBE_SCOPES

load_dotenv()

client_id = os.environ["YOUTUBE_CLIENT_ID"]
client_secret = os.environ["YOUTUBE_CLIENT_SECRET"]

client_config = {
    "installed": {
        "client_id": client_id,
        "client_secret": client_secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=YOUTUBE_SCOPES)
creds = flow.run_local_server(
    port=0,
    access_type="offline",
    prompt="consent",
    open_browser=True,
)

if not creds.refresh_token:
    raise SystemExit(
        "No refresh_token returned. Revoke the app at "
        "https://myaccount.google.com/permissions and re-run."
    )

token_blob = {"token": creds.token, "refresh_token": creds.refresh_token}
print("\n=== Paste this single line into .env as YOUTUBE_OAUTH_TOKEN=<value> ===\n")
print(json.dumps(token_blob))
