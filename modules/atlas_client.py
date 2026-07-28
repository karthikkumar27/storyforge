"""One implementation of the Atlas Cloud prediction protocol.

Every Atlas model — image, image edit, video, all Seedance variants — speaks the
same three-step protocol: POST a request and get a prediction id back, poll that
id until it reports completed or failed, then read `outputs`. This module is the
only place that protocol lives.

Before this existed there were seven copies of it, which had drifted into five
different opinions about what an HTTP 400 from the prediction endpoint means.
The policy here is the best of the seven:

  400 / 500   parse the body. Atlas serves hard task failures (content filter,
              model error, fetch failure) as 400/500 with the reason in JSON, so
              a structured failure is terminal. An unstructured one is a gateway
              blip — back off and retry.
  429         rate limited; back off 60s.
  502-504     gateway; back off 30s.
  read timeout  the prediction endpoint sometimes hangs under load. The task is
              still running server-side, so resume polling rather than failing.
  content filter  raised as AtlasContentFilterError so a caller can soften its
              prompt and retry, rather than having to string-match the message.

Poll cadence stays a per-call argument: image generation settles in seconds,
video takes minutes, and polling video every 2s earns a 429.

Both the HTTP client and the sleep function are injected so tests can drive the
retry paths without waiting on a real clock.
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from config import ATLAS_BASE_URL, ATLAS_MAX_POLL_ATTEMPTS, ATLAS_POLL_INTERVAL_SEC

# Backoffs, in seconds, for the transient cases.
RATE_LIMIT_BACKOFF = 60
GATEWAY_BACKOFF = 30

# Substrings that mark a rejection as a content-filter refusal rather than a
# genuine error. Kept deliberately narrow — "content" alone matches things like
# "content-type", which is not a refusal.
_CONTENT_FILTER_MARKERS = (
    "content safety",
    "safety policy",
    "content policy",
    "content filter",
    "sensitivecontent",
)


class AtlasError(RuntimeError):
    """Any failure talking to Atlas Cloud."""


class AtlasTaskFailed(AtlasError):
    """The prediction reached a terminal failed state."""


class AtlasContentFilterError(AtlasTaskFailed):
    """The prompt was refused by the model's content filter.

    Distinct from other failures because it is worth retrying with softened
    wording, which is exactly what the image generator does.
    """


class AtlasTimeout(AtlasError):
    """The prediction did not settle within the allowed number of polls."""


def _looks_like_content_filter(text: str) -> bool:
    lowered = str(text).lower()
    return any(marker in lowered for marker in _CONTENT_FILTER_MARKERS)


class AtlasClient:
    """Submit a prediction, wait for it, read the outputs, fetch the file.

    Four methods:
        submit()         request -> prediction id
        await_outputs()  prediction id -> list of output URLs
        run()            both of the above, the common case
        download()       output URL -> local file
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        http: Any = httpx,
        sleep: Any = time.sleep,
        max_attempts: int | None = None,
        poll_interval: float | None = None,
        base_url: str = ATLAS_BASE_URL,
    ):
        self._api_key = api_key or os.environ["ATLASCLOUD_API_KEY"]
        self._http = http
        self._sleep = sleep
        self._max_attempts = max_attempts or ATLAS_MAX_POLL_ATTEMPTS
        self._poll_interval = poll_interval or ATLAS_POLL_INTERVAL_SEC
        self._base_url = base_url

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # -- submit ---------------------------------------------------------------

    def submit(self, endpoint: str, body: dict, *, label: str = "Atlas") -> str:
        """POST a generation request and return its prediction id.

        A 429 here is retried with a rate-limit backoff; anything else in the
        4xx/5xx range is terminal, since we have no prediction to poll.
        """
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        for attempt in range(self._max_attempts):
            resp = self._http.post(url, headers=self._headers, json=body, timeout=60)
            if resp.status_code == 429:
                print(
                    f"[{label}] Submit rate limited, backing off {RATE_LIMIT_BACKOFF}s...",
                    flush=True,
                )
                self._sleep(RATE_LIMIT_BACKOFF)
                continue
            if resp.status_code >= 400:
                detail = resp.text[:500]
                message = f"{label} submit failed: HTTP {resp.status_code} — {detail}"
                if _looks_like_content_filter(detail):
                    raise AtlasContentFilterError(message)
                raise AtlasError(message)
            prediction_id = resp.json()["data"]["id"]
            print(f"[{label}] Task created: {prediction_id}", flush=True)
            return prediction_id
        raise AtlasTimeout(f"{label} submit rate limited on every attempt")

    # -- poll -----------------------------------------------------------------

    def await_outputs(
        self,
        prediction_id: str,
        *,
        poll_interval: float | None = None,
        label: str = "Atlas",
    ) -> list[str]:
        """Poll a prediction until it completes, and return its outputs."""
        interval = poll_interval if poll_interval is not None else self._poll_interval
        url = f"{self._base_url}/model/prediction/{prediction_id}"

        for attempt in range(self._max_attempts):
            try:
                resp = self._http.get(url, headers=self._headers, timeout=30)
            except httpx.TimeoutException as exc:
                # The prediction endpoint hangs under load. The task is still
                # cooking server-side, so resume rather than losing a paid run.
                print(
                    f"[{label}] Poll read timeout ({type(exc).__name__}), "
                    f"retrying in {interval}s...",
                    flush=True,
                )
                self._sleep(interval)
                continue

            retry_after = self._transient_backoff(resp, label)
            if retry_after is not None:
                self._sleep(retry_after)
                continue

            resp.raise_for_status()
            data = resp.json()["data"]
            status = data.get("status")

            if status == "completed":
                outputs = data.get("outputs") or []
                if not outputs:
                    raise AtlasTaskFailed(
                        f"{label} task {prediction_id} completed but returned no outputs: {data}"
                    )
                print(f"[{label}] Task {prediction_id} completed", flush=True)
                return list(outputs)

            if status == "failed":
                error = data.get("error", "unknown error")
                message = f"{label} task {prediction_id} failed: {error}"
                if _looks_like_content_filter(error):
                    raise AtlasContentFilterError(message)
                raise AtlasTaskFailed(message)

            if attempt % 4 == 0:
                print(f"[{label}] Task {prediction_id} status: {status}, waiting...", flush=True)
            self._sleep(interval)

        raise AtlasTimeout(
            f"{label} task {prediction_id} timed out after "
            f"{self._max_attempts} polls at {interval}s"
        )

    def _transient_backoff(self, resp: Any, label: str) -> float | None:
        """Return how long to back off before re-polling, or None to carry on.

        Raises when the response describes a terminal task failure.
        """
        code = resp.status_code

        if code == 429:
            print(f"[{label}] Poll HTTP 429 (rate limit), backing off {RATE_LIMIT_BACKOFF}s...", flush=True)
            return RATE_LIMIT_BACKOFF

        if code in (502, 503, 504):
            print(f"[{label}] Poll HTTP {code} (gateway), backing off {GATEWAY_BACKOFF}s...", flush=True)
            return GATEWAY_BACKOFF

        if code in (400, 500):
            # Atlas reports hard task failures here with the reason in the body.
            # A structured failure is terminal; anything else is a gateway blip.
            detail = resp.text[:500]
            try:
                payload = resp.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                inner = (payload.get("data") or {}).get("status")
                message = payload.get("message") or payload.get("error") or ""
                if inner == "failed" or message:
                    print(f"[{label}] Poll HTTP {code} (TASK FAILED): {detail}", flush=True)
                    text = f"{message or detail}"
                    if _looks_like_content_filter(text):
                        raise AtlasContentFilterError(f"{label} refused by content filter: {text}")
                    raise AtlasTaskFailed(f"{label} task failed: {text}")
            print(
                f"[{label}] Poll HTTP {code} (unstructured), backing off {GATEWAY_BACKOFF}s...",
                flush=True,
            )
            return GATEWAY_BACKOFF

        return None

    # -- the common case ------------------------------------------------------

    def run(
        self,
        endpoint: str,
        body: dict,
        *,
        poll_interval: float | None = None,
        label: str = "Atlas",
    ) -> list[str]:
        """Submit a request and wait for its outputs."""
        prediction_id = self.submit(endpoint, body, label=label)
        return self.await_outputs(prediction_id, poll_interval=poll_interval, label=label)

    # -- fetching the result --------------------------------------------------

    def download(self, url: str, path: str, *, timeout: float = 180) -> str:
        """Stream an output URL to a local path and return that path."""
        with self._http.stream("GET", url, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(path, "wb") as handle:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    handle.write(chunk)
        return path
