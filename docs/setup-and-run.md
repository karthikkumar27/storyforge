# Setup & Run Guide — idea-creator

End-to-end guide for configuring environment variables and running the pipeline locally or on Cloud Run. Based on the actual code in this repo as of April 2026.

---

## 1. What the pipeline does

`idea-creator` is a hands-off story-video generator:

1. **Read** a pending story brief from a Google Sheet (`modules/gsheet_reader.py`)
2. **Generate** a script from the brief via Claude (`modules/brief_generator.py`, `modules/script_generator.py`)
3. **Produce** video shots via Kling AI (`modules/video_producer.py`)
4. **Mix** audio/TTS via ElevenLabs + royalty-free music (`modules/audio_mixer.py`)
5. **Upload** the final video to YouTube (`modules/youtube_uploader.py`)

The HTTP entry point is `main.py`, exposing `POST /run` and `GET /health` for Cloud Run.

---

## 2. Environment variables

All secrets are read from `os.environ` at module init. Locally, `main.py:6` calls `load_dotenv()` so a `.env` file at the repo root is picked up automatically. On Cloud Run, the same variables should be injected via **Secret Manager → env var bindings** (never baked into the Dockerfile).

### 2.1 Full list

| Variable | Required? | Read in | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | `brief_generator.py`, `script_generator.py`, `discovery.py` | Claude API auth |
| `GOOGLE_SHEET_ID` | Yes | `gsheet_reader.py` | Target spreadsheet ID |
| `GOOGLE_SHEETS_CREDENTIALS` | Yes | `gsheet_reader.py` | Service account JSON (full blob, single line) |
| `KLING_ACCESS_KEY_ID` | Yes | `video_producer.py` | Kling video API key |
| `KLING_SECRET_KEY` | Yes | `video_producer.py` | Kling video API secret |
| `YOUTUBE_CLIENT_ID` | Yes | `youtube_uploader.py` | OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | Yes | `youtube_uploader.py` | OAuth client secret |
| `YOUTUBE_OAUTH_TOKEN` | Yes | `youtube_uploader.py` | OAuth token JSON (full blob, single line) |
| `ELEVENLABS_API_KEY` | Optional | `audio_mixer.py` | TTS — pipeline continues silently if blank |
| `PORT` | Optional (defaults to `8080`) | `main.py` | Local Flask port; Cloud Run injects its own |

**Fail-fast note:** all "Yes" entries use `os.environ["X"]` (strict), so missing keys raise `KeyError` at startup. Empty strings, however, do **not** raise — they surface later as downstream 401s from the respective API.

### 2.2 Create `.env` for local development

At the repo root, create `.env` with these placeholders:

```env
# Anthropic / Claude
ANTHROPIC_API_KEY=

# Google Sheets (source of story briefs)
GOOGLE_SHEET_ID=
# Paste the full service-account JSON on ONE line (no newlines)
GOOGLE_SHEETS_CREDENTIALS=

# Kling (video generation)
KLING_ACCESS_KEY_ID=
KLING_SECRET_KEY=

# YouTube upload
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
# Paste the full OAuth token JSON on ONE line (no newlines)
YOUTUBE_OAUTH_TOKEN=

# ElevenLabs (TTS / audio) — optional
ELEVENLABS_API_KEY=

# Local Flask port (Cloud Run injects its own PORT)
PORT=8080
```

Make sure `.env` is listed in `.gitignore` — **never** commit this file.

---

## 3. How to obtain each credential

### 3.1 `ANTHROPIC_API_KEY`

1. Go to https://console.anthropic.com/settings/keys
2. Click **Create Key**, name it (e.g. `idea-creator`), copy the `sk-ant-...` value
3. Paste into `.env`

### 3.2 `GOOGLE_SHEET_ID`

Open the sheet in your browser. The ID is the long alphanumeric string in the URL between `/d/` and the next `/`:

```
https://docs.google.com/spreadsheets/d/1AbC2dEfGhIjKlMnOpQrStUvWxYz1234567890abcdef/edit#gid=0
                                      └──────────────── this part ─────────────────┘
```

Copy only that segment — no `/edit`, no `#gid=...`. (`gid` is the tab ID, not needed here.)

### 3.3 `GOOGLE_SHEETS_CREDENTIALS`

This is a **Google Cloud service account JSON key**, pasted as a single-line blob.

1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts (select the right project)
2. Click **Create Service Account** (or pick an existing one)
3. On the service account row → **Keys** tab → **Add Key → Create new key → JSON**
4. A JSON file downloads. Convert it to a single line:
   ```bash
   python -c "import json; print(json.dumps(json.load(open('path/to/creds.json'))))"
   ```
5. Paste the output as the value of `GOOGLE_SHEETS_CREDENTIALS=` in `.env`

**Critical**: open the target Google Sheet, click **Share**, paste the service account email (`client_email` field in the JSON, e.g. `video-generator@<project>.iam.gserviceaccount.com`), and grant **Editor** access. Without this, `gspread` returns 403 even with valid credentials.

⚠️ `python-dotenv` stops reading the value at the first newline. Multi-line JSON in `.env` will silently corrupt the blob — always collapse to one line.

### 3.4 `KLING_ACCESS_KEY_ID` + `KLING_SECRET_KEY`

1. Go to https://app.klingai.com → sign in
2. Navigate to **Account → API Management**
3. Click **Create AccessKey**, copy both the ID and secret
4. Paste into `.env`

Note: Kling's API portal is separate from the consumer app. Access may require a paid API tier and/or account approval.

### 3.5 `YOUTUBE_CLIENT_ID` + `YOUTUBE_CLIENT_SECRET`

These come from an **OAuth 2.0 Client** in Google Cloud Console. Use the same project as your service account.

**Step 1 — Enable the API:**
- Go to https://console.cloud.google.com/apis/library/youtube.googleapis.com
- Confirm the correct project is selected → click **Enable**

**Step 2 — Configure the OAuth consent screen** (one-time):
- Go to https://console.cloud.google.com/apis/credentials/consent
- Choose **External** → fill in app name + support email
- Under **Scopes**, add `https://www.googleapis.com/auth/youtube.upload`
- Under **Test users**, add the Google account that owns the target YouTube channel
- Save. Leave publishing status as **Testing** — no verification needed for personal use

**Step 3 — Create the OAuth Client ID:**
- Go to https://console.cloud.google.com/apis/credentials
- **+ Create Credentials → OAuth client ID**
- Application type: **Desktop app** (important — enables the localhost loopback flow used by `generate_youtube_token.py`)
- Name it `idea-creator-uploader`, click **Create**
- Copy the **Client ID** and **Client Secret** from the dialog → paste into `.env`

### 3.6 `YOUTUBE_OAUTH_TOKEN`

Unlike the other secrets, this one cannot be copy-pasted from a dashboard. It's a refresh token minted by running a one-shot OAuth flow locally.

The repo includes `generate_youtube_token.py` for this. Prerequisites:
- `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` already filled in `.env`
- Python venv active, deps installed (`pip install -r requirements.txt`)

Run it:

```bash
cd /path/to/idea-creator
python generate_youtube_token.py
```

What happens:
1. A browser tab opens to Google's consent screen
2. Log in with **the Google account that owns the YouTube channel you want to upload to** — not your service account, not a different dev account
3. You'll see a warning "Google hasn't verified this app" → click **Advanced → Go to [app name] (unsafe)**. This is expected for Testing-mode consent screens; it's your own app.
4. Grant the `youtube.upload` scope
5. Browser redirects to `localhost` and shows "The authentication flow has completed"
6. The terminal prints a single-line JSON blob like `{"token": "ya29...", "refresh_token": "1//0g..."}`

Copy that entire line (including the braces) and paste as the value of `YOUTUBE_OAUTH_TOKEN=` in `.env`.

**Why only two fields?** `youtube_uploader.py:15-22` reconstructs the `Credentials` object from env vars — it only reads `token` and `refresh_token` from the blob. Everything else (client_id, scopes, token_uri) comes from other env vars and `config.py`.

**Token expiry:**
- The `token` field expires in ~1 hour, but `youtube_uploader.py:23-24` calls `creds.refresh(Request())` on startup to mint a fresh access token from the refresh token. So the `token` value is effectively throwaway — only `refresh_token` matters long-term.
- In Testing-mode OAuth apps, refresh tokens expire after **7 days**. You'll need to re-run `generate_youtube_token.py` weekly. For production you'd submit the app for verification.

**Common errors:**

| Error | Cause | Fix |
|---|---|---|
| `No refresh_token returned` | Previously authorized this OAuth client with the same account | Revoke at https://myaccount.google.com/permissions → re-run |
| `Access blocked: [app] has not completed verification` (no Advanced link) | Account isn't in Test users list | Add it on the consent screen |
| `invalid_scope` | Scope not listed on consent screen | Edit App → Scopes → add `https://www.googleapis.com/auth/youtube.upload` |

### 3.7 `ELEVENLABS_API_KEY` (optional)

1. Go to https://elevenlabs.io/app/settings/api-keys
2. **Create API Key** → copy
3. Paste into `.env`

`audio_mixer.py:13` uses `os.environ.get(...)` so this is optional — the pipeline will continue without TTS if blank, but you won't get voiceover.

---

## 4. Running the code

### 4.1 Local development

```bash
cd /path/to/idea-creator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Make sure .env is filled in
python main.py
```

Flask starts on `http://0.0.0.0:8080`. Test the endpoints:

```bash
# Health check
curl http://localhost:8080/health
# → {"status": "ok"}

# Run the full pipeline (reads next pending row → generates → uploads)
curl -X POST http://localhost:8080/run
# → JSON result with video URL, or {"error": "..."} on failure
```

The Flask error handler in `main.py:16-17` returns the exception message directly as JSON — useful for debugging env var issues without digging through stack traces.

### 4.2 Testing individual modules

If the full `/run` fails, test modules in isolation before burning Kling/ElevenLabs credits:

```bash
python -i
>>> from modules.gsheet_reader import GSheetReader
>>> rows = GSheetReader().fetch_pending()
>>> # ... and so on for brief_generator, script_generator, etc.
```

Suggested test order (cheap → expensive):
1. `gsheet_reader` (free, catches sheet sharing issues)
2. `brief_generator` + `script_generator` (Claude tokens, cheap)
3. `video_producer` (Kling, $$)
4. `audio_mixer` (ElevenLabs, $)
5. `youtube_uploader` (free, but publishes publicly — test with `privacyStatus: private` first if unsure)

### 4.3 Deploying to Cloud Run

The repo includes a `Dockerfile` with ffmpeg baked in. Do **not** put secrets in the Dockerfile — bind them via Secret Manager.

**One-time: create each secret in Secret Manager:**
```bash
echo -n "sk-ant-..." | gcloud secrets create ANTHROPIC_API_KEY --data-file=-
echo -n "1AbC..."    | gcloud secrets create GOOGLE_SHEET_ID --data-file=-
# ... repeat for each variable
```

For JSON-blob vars, pipe the single-line JSON:
```bash
python -c "import json; print(json.dumps(json.load(open('creds.json'))))" \
  | gcloud secrets create GOOGLE_SHEETS_CREDENTIALS --data-file=-
```

**Deploy and bind secrets:**
```bash
gcloud run deploy idea-creator \
  --source . \
  --region asia-southeast1 \
  --update-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,\
GOOGLE_SHEET_ID=GOOGLE_SHEET_ID:latest,\
GOOGLE_SHEETS_CREDENTIALS=GOOGLE_SHEETS_CREDENTIALS:latest,\
KLING_ACCESS_KEY_ID=KLING_ACCESS_KEY_ID:latest,\
KLING_SECRET_KEY=KLING_SECRET_KEY:latest,\
YOUTUBE_CLIENT_ID=YOUTUBE_CLIENT_ID:latest,\
YOUTUBE_CLIENT_SECRET=YOUTUBE_CLIENT_SECRET:latest,\
YOUTUBE_OAUTH_TOKEN=YOUTUBE_OAUTH_TOKEN:latest,\
ELEVENLABS_API_KEY=ELEVENLABS_API_KEY:latest
```

The Cloud Run service account needs `roles/secretmanager.secretAccessor` on each secret. `PORT` is injected by Cloud Run automatically — don't set it.

---

## 5. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `KeyError` at startup | Missing env var in `.env` | Check spelling against the table in §2.1 |
| `gspread.exceptions.APIError: 403` | Sheet not shared with service account | Share with `client_email` from the service account JSON |
| Claude 401 | `ANTHROPIC_API_KEY` empty or revoked | Regenerate at console.anthropic.com |
| YouTube upload 401 after ~1hr | Refresh token expired (7-day window in Testing mode) | Re-run `generate_youtube_token.py`, re-paste `YOUTUBE_OAUTH_TOKEN` |
| Kling job stuck pending | `video_producer.py` polls with `POLL_INTERVAL_SEC=10`, `MAX_POLL_ATTEMPTS=60` → gives up after 10 min | Check Kling dashboard for job status; increase `MAX_POLL_ATTEMPTS` in `config.py` if jobs legitimately take longer |
| `GOOGLE_SHEETS_CREDENTIALS` parses but auth fails | Multi-line JSON in `.env` got truncated at first newline | Re-paste as single line |

---

## 6. Security notes

- `.env` contains long-lived credentials for **five different paid services plus a YouTube upload token**. Treat it like a password file.
- The service account JSON and YouTube refresh token are the highest-value items — both can be revoked from their respective dashboards if leaked.
- Never commit `.env`, `generate_youtube_token.py` output, or terminal history containing these values.
- On Cloud Run, prefer Secret Manager over `--set-env-vars` — secrets set via `--set-env-vars` show up in the revision YAML and are visible to anyone with `run.revisions.get`.
