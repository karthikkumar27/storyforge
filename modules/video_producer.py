import os
import shutil
import time
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Any, Protocol

import httpx

from config import (
    VIDEO_PROVIDER,
    SHOT_DURATION, ASPECT_RATIO,
    ATLAS_VIDEO_MODEL_I2V, ATLAS_VIDEO_MODEL_T2V,
    ATLAS_VIDEO_MODEL_SEEDANCE_2_T2V, ATLAS_VIDEO_MODEL_SEEDANCE_2_I2V,
    ATLAS_VIDEO_MODEL_SEEDANCE_1_5_T2V_FAST,
    KLING_BASE_URL, KLING_MODEL, KLING_POLL_INTERVAL_SEC, KLING_MAX_POLL_ATTEMPTS,
    SEEDANCE_MODEL, SEEDANCE_BASE_URL, SEEDANCE_RESOLUTION,
    SEEDANCE_POLL_INTERVAL_SEC, SEEDANCE_MAX_POLL_ATTEMPTS,
)
from modules.atlas_client import AtlasClient


class StoryboardSupplier(Protocol):
    """Yields the first-frame still for one shot, given what came before.

    `previous_clip` is None for the first shot. Returning None means "no
    storyboard for this shot" and the producer falls back to the shared
    reference image.
    """

    def frame_for(
        self, index: int, shot_prompt: str, previous_clip: str | None
    ) -> str | None:
        ...


class BaseVideoProducer(ABC):
    @abstractmethod
    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        ...

    @abstractmethod
    def _poll_shot(self, task_id: str) -> str:
        ...

    def _download_clip(self, url: str, path: str) -> None:
        with httpx.stream("GET", url, timeout=120) as resp:
            resp.raise_for_status()
            with open(path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)

    def _stitch(
        self,
        clip_paths: list[str],
        output_path: str,
        title_card: str | None = None,
        end_card: str | None = None,
    ) -> None:
        """Concat shots into one MP4, optionally prepending a title card and
        appending an end card.

        Without cards: uses fast `-c copy` (assumes all shots share format).
        With cards: re-encodes via filter_complex concat so format mismatches
        between externally-built cards and AI-generated shots don't break playback.
        """
        all_paths = []
        if title_card:
            all_paths.append(title_card)
        all_paths.extend(clip_paths)
        if end_card:
            all_paths.append(end_card)

        # Fast path — pure shots, all from same source (all h264 from Seedance/Kling)
        if not title_card and not end_card:
            concat_file = os.path.join(os.path.dirname(output_path), "concat.txt")
            with open(concat_file, "w") as f:
                for p in all_paths:
                    f.write(f"file '{p}'\n")
            subprocess.run(
                ["ffmpeg", "-f", "concat", "-safe", "0", "-i", concat_file,
                 "-c", "copy", output_path, "-y"],
                check=True,
                capture_output=True,
            )
            return

        # Cards present — re-encode via filter_complex concat for reliable playback
        # across mixed sources (renderer-built MP4s vs Atlas-generated shots).
        # The concat filter requires every input to share the same dimensions,
        # framerate, sample rate, and channel layout. Seedance shots and our
        # cards may differ on any of these (e.g. shots come back at 496x864
        # while cards build at 270x480). We normalise every input stream first.
        target_w, target_h = self._probe_video_size(clip_paths[0])
        target_fps = 24
        target_sr = 44100
        target_ch = 2

        cmd = ["ffmpeg", "-y"]
        for p in all_paths:
            cmd += ["-i", str(p)]

        n = len(all_paths)
        # For each input, scale + pad video to target size, normalise framerate,
        # and resample audio to a consistent rate/channel layout.
        normalise_steps = []
        for i in range(n):
            normalise_steps.append(
                f"[{i}:v:0]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black,"
                f"setsar=1,fps={target_fps},format=yuv420p[v{i}]"
            )
            normalise_steps.append(
                f"[{i}:a:0]aresample={target_sr},aformat=channel_layouts=stereo[a{i}]"
            )
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
        filter_complex = (
            ";".join(normalise_steps)
            + f";{concat_inputs}concat=n={n}:v=1:a=1[outv][outa]"
        )

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", str(target_sr),
            "-movflags", "+faststart",
            output_path,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode()[-800:] if exc.stderr else ""
            raise RuntimeError(f"Stitch with cards failed: {stderr}") from exc

    @staticmethod
    def _probe_video_size(path: str) -> tuple[int, int]:
        """Return (width, height) of the video stream in path."""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(path),
            ],
            check=True, capture_output=True, text=True,
        )
        w_str, h_str = result.stdout.strip().split("x")
        return int(w_str), int(h_str)

    def produce(
        self,
        shots: list[str],
        reference_image_url: str | None = None,
        storyboard_urls: list[str] | None = None,
        storyboard_supplier: "StoryboardSupplier | None" = None,
    ) -> str:
        """Produce a stitched video from a list of shot prompts.

        Three modes for first-frame anchoring, in priority order:

        - **Chained (preset-9)**: caller passes `storyboard_supplier`. It is
          called once per shot with the PREVIOUS shot's clip, so each
          storyboard can carry character identity forward from what actually
          rendered. Requires the shot loop and the storyboard loop to
          interleave, which is why this is a callback rather than a list.

        - **Premium (preset-7)**: caller passes `storyboard_urls` — one URL per
          shot, generated upstream before production starts. Each shot is
          anchored to its own shot-appropriate frame, giving locked character
          identity AND varied starting poses.

        - **Legacy**: caller passes a single `reference_image_url` — used as
          the first frame for all shots (other presets, or fallback when
          storyboard generation fails).
        """
        workdir = tempfile.mkdtemp(prefix="cinematic_")
        try:
            clip_paths = []
            previous_clip: str | None = None
            for i, prompt in enumerate(shots):
                print(f"[VideoProducer] Submitting shot {i+1}/{len(shots)}", flush=True)
                ref_url = self._anchor_for(
                    i, prompt, previous_clip, storyboard_urls,
                    reference_image_url, storyboard_supplier,
                )
                task_id = self._submit_shot(prompt, ref_url)
                print(f"[VideoProducer] Polling task {task_id}...", flush=True)
                video_url = self._poll_shot(task_id)
                clip_path = os.path.join(workdir, f"shot_{i:02d}.mp4")
                self._download_clip(video_url, clip_path)
                clip_paths.append(clip_path)
                previous_clip = clip_path
                print(f"[VideoProducer] Shot {i+1} downloaded", flush=True)

            # Optional title/end cards — built once and cached, reused across episodes.
            title_card = self._get_title_card()
            end_card = self._get_end_card()

            output_path = os.path.join(workdir, "stitched.mp4")
            self._stitch(
                clip_paths,
                output_path,
                title_card=str(title_card) if title_card else None,
                end_card=str(end_card) if end_card else None,
            )
            label = f"{len(shots)} shots"
            if title_card:
                label += " + title card"
            if end_card:
                label += " + end card"
            print(f"[VideoProducer] Stitched {label}", flush=True)
            return output_path
        except Exception:
            # Preserve the workdir on failure so the (already paid for) shots
            # can be reused for a manual stitch retry. The OS sweeps temp
            # folders eventually; a stuck folder costs nothing locally.
            print(f"[VideoProducer] FAILED — shots preserved at {workdir}", flush=True)
            raise

    def _anchor_for(
        self,
        index: int,
        prompt: str,
        previous_clip: str | None,
        storyboard_urls: list[str] | None,
        reference_image_url: str | None,
        supplier: "StoryboardSupplier | None",
    ) -> str | None:
        """Resolve one shot's first frame. Never raises — an anchor is an
        enhancement, and losing it costs pose variety, not the episode."""
        if supplier is not None:
            try:
                url = supplier.frame_for(index, prompt, previous_clip)
            except Exception as exc:
                print(
                    f"[VideoProducer]   shot {index+1} supplier failed ({exc}) "
                    f"— falling back to the shared reference",
                    flush=True,
                )
                url = None
            if url:
                print(f"[VideoProducer]   shot {index+1} anchor: chained storyboard", flush=True)
                return url

        if storyboard_urls and index < len(storyboard_urls) and storyboard_urls[index]:
            print(f"[VideoProducer]   shot {index+1} anchor: per-shot storyboard", flush=True)
            return storyboard_urls[index]

        if reference_image_url:
            print(f"[VideoProducer]   shot {index+1} anchor: shared locked ref", flush=True)
        return reference_image_url

    def _get_title_card(self):
        """Resolve the active preset's title card (built once, cached forever)."""
        from modules.preset import active_preset
        cfg = active_preset().title_card
        if not cfg:
            return None
        from modules.title_card_renderer import build_card
        resolution = self._card_resolution()
        return build_card(cfg, resolution=resolution, aspect_ratio=ASPECT_RATIO, kind="title")

    def _get_end_card(self):
        """Resolve the active preset's end card (built once, cached forever)."""
        from modules.preset import active_preset
        cfg = active_preset().end_card
        if not cfg:
            return None
        from modules.title_card_renderer import build_card
        resolution = self._card_resolution()
        return build_card(cfg, resolution=resolution, aspect_ratio=ASPECT_RATIO, kind="end")

    def _card_resolution(self) -> str:
        """Match the resolution we render shots at (provider-specific)."""
        if VIDEO_PROVIDER == "atlas":
            return "720p"
        if VIDEO_PROVIDER == "seedance":
            return SEEDANCE_RESOLUTION
        return "720p"


class KlingVideoProducer(BaseVideoProducer):
    """Kling AI, one prediction per shot. Legacy provider — kept working, not
    on the active path for any current preset."""

    def __init__(
        self,
        access_key_id: str | None = None,
        secret_key: str | None = None,
        *,
        http: Any = httpx,
        sleep: Any = time.sleep,
    ):
        import jwt
        self._jwt = jwt
        # Credentials resolve at construction, but only when not supplied — so
        # a test can build one without KLING_* in the environment.
        self.access_key_id = access_key_id or os.environ["KLING_ACCESS_KEY_ID"]
        self.secret_key = secret_key or os.environ["KLING_SECRET_KEY"]
        self._http = http
        self._sleep = sleep

    def _jwt_token(self) -> str:
        now = int(time.time())
        payload = {"iss": self.access_key_id, "exp": now + 1800, "nbf": now - 5}
        return self._jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._jwt_token()}",
            "Content-Type": "application/json",
        }

    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        resp = self._http.post(
            f"{KLING_BASE_URL}/v1/videos/text2video",
            headers=self._headers(),
            json={"model": KLING_MODEL, "prompt": prompt,
                  "duration": SHOT_DURATION, "aspect_ratio": ASPECT_RATIO},
            timeout=30,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Kling submit failed: HTTP {resp.status_code} — body: {resp.text}"
            )
        return resp.json()["data"]["task_id"]

    def _poll_shot(self, task_id: str) -> str:
        for _ in range(KLING_MAX_POLL_ATTEMPTS):
            resp = self._http.get(
                f"{KLING_BASE_URL}/v1/videos/text2video/{task_id}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()["data"]
            if data["task_status"] == "succeed":
                return data["videos"][0]["url"]
            if data["task_status"] == "failed":
                raise RuntimeError(f"Kling task {task_id} failed")
            self._sleep(KLING_POLL_INTERVAL_SEC)
        raise TimeoutError(f"Kling task {task_id} timed out after {KLING_MAX_POLL_ATTEMPTS} polls")


class SeedanceVideoProducer(BaseVideoProducer):
    """Seedance 1.0 Pro via the BytePlus Ark SDK. Legacy provider (v1)."""

    def __init__(self, client: Any = None, *, sleep: Any = time.sleep):
        self.client = client or self._build_client()
        self._sleep = sleep

    @staticmethod
    def _build_client():
        from byteplussdkarkruntime import Ark
        return Ark(
            base_url=SEEDANCE_BASE_URL,
            api_key=os.environ["ARK_API_KEY"],
        )

    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        content = [{"type": "text", "text": prompt}]

        if reference_image_url:
            content.append({
                "type": "image_url",
                "image_url": {"url": reference_image_url},
                "role": "first_frame",
            })

        result = self.client.content_generation.tasks.create(
            model=SEEDANCE_MODEL,
            content=content,
            ratio=ASPECT_RATIO,
            resolution=SEEDANCE_RESOLUTION,
            duration=SHOT_DURATION,
        )
        print(f"[Seedance] Task created: {result.id}", flush=True)
        return result.id

    def _poll_shot(self, task_id: str) -> str:
        for attempt in range(SEEDANCE_MAX_POLL_ATTEMPTS):
            task = self.client.content_generation.tasks.get(task_id=task_id)
            status = task.status
            if status == "succeeded":
                content = task.content
                print(f"[Seedance] Task {task_id} succeeded", flush=True)
                if isinstance(content, list):
                    for item in content:
                        url = getattr(item, "video_url", None)
                        if url:
                            return url if isinstance(url, str) else url.url
                else:
                    url = getattr(content, "video_url", None)
                    if url:
                        return url if isinstance(url, str) else url.url
                raise RuntimeError(
                    f"Seedance task {task_id} succeeded but no video URL found: {content}"
                )
            if status == "failed":
                error_msg = getattr(task, "error", None) or "unknown error"
                raise RuntimeError(f"Seedance task {task_id} failed: {error_msg}")
            if attempt % 2 == 0:
                print(f"[Seedance] Task {task_id} status: {status}, waiting...", flush=True)
            self._sleep(SEEDANCE_POLL_INTERVAL_SEC)
        raise TimeoutError(
            f"Seedance task {task_id} timed out after {SEEDANCE_MAX_POLL_ATTEMPTS * SEEDANCE_POLL_INTERVAL_SEC}s"
        )


class AtlasVideoProducer(BaseVideoProducer):
    """Seedance 1.5 Pro via Atlas Cloud, one prediction per shot."""

    def __init__(self, client: AtlasClient | None = None):
        self._atlas = client or AtlasClient()

    def _submit_shot(self, prompt: str, reference_image_url: str | None = None) -> str:
        if reference_image_url:
            model = ATLAS_VIDEO_MODEL_I2V
            print("[Atlas] Using image-to-video (shot with reference)", flush=True)
        else:
            model = ATLAS_VIDEO_MODEL_T2V
            print("[Atlas] Using text-to-video (no reference image)", flush=True)

        body = {
            "model": model,
            "prompt": prompt,
            "duration": SHOT_DURATION,
            "resolution": "720p",
            "aspect_ratio": ASPECT_RATIO,
        }
        if reference_image_url:
            body["image"] = reference_image_url

        return self._atlas.submit("model/generateVideo", body, label="Atlas")

    def _poll_shot(self, task_id: str) -> str:
        return self._atlas.await_outputs(task_id, label="Atlas")[0]


def create_video_producer() -> BaseVideoProducer:
    if VIDEO_PROVIDER == "atlas":
        print("[VideoProducer] Using Atlas Cloud — Seedance 2.0 Fast", flush=True)
        return AtlasVideoProducer()
    if VIDEO_PROVIDER == "kling":
        print("[VideoProducer] Using Kling backend", flush=True)
        return KlingVideoProducer()
    print("[VideoProducer] Using BytePlus Seedance 1.0 Pro backend", flush=True)
    return SeedanceVideoProducer()


class AtlasSeedance2I2VLoopProducer:
    """Single-clip image-to-video via Seedance 2.0 with native audio, producing
    a SEAMLESS NATURAL LOOP.

    The looping mechanism is native to the Seedance 2.0 i2v API: we pass the
    same image URL as both `image` (first frame) and `last_image` (last frame).
    The model is conditioned to choreograph motion that begins at that image,
    drifts through `duration` seconds, and lands back on the same image. The
    loop is baked into the generated frames — no crossfade, palindrome, or
    other post-processing trick.

    Used by the `single_shot_native` pipeline mode (preset-8). Does NOT extend
    BaseVideoProducer — no shot list, no stitcher. Seedance also generates
    matching ambient audio in the same call (generate_audio=True), so the
    orchestrator skips the audio mixer too.
    """

    def __init__(self, client: AtlasClient | None = None):
        self._atlas = client or AtlasClient()

    def produce(self, image_url: str, motion_prompt: str, params: dict) -> str:
        """Submit a Seedance 2.0 i2v loop request, poll, download, return
        local MP4 path.

        Args:
          image_url:     Public URL of the start/end frame still. Passed as both
                         `image` and `last_image` so the loop is natural.
          motion_prompt: Text describing the cyclic camera motion + ambient
                         audio cues. The brief from preset-8's brief_system
                         already satisfies the required shape.
          params:        The preset's `seedance2` config dict (duration,
                         resolution, ratio, generate_audio, watermark).
        """
        body = {
            "model": ATLAS_VIDEO_MODEL_SEEDANCE_2_I2V,
            "prompt": motion_prompt,
            "image": image_url,
            "last_image": image_url,   # same image → forces natural loop
            "duration": params.get("duration", 12),
            "resolution": params.get("resolution", "720p-SR"),
            "ratio": params.get("ratio", "9:16"),
            "generate_audio": params.get("generate_audio", True),
            "watermark": params.get("watermark", False),
            "return_last_frame": False,
        }
        print(
            f"[Seedance2-Loop] Submitting i2v: duration={body['duration']}s "
            f"resolution={body['resolution']} ratio={body['ratio']} "
            f"audio={body['generate_audio']} loop_anchor={image_url[:60]}...",
            flush=True,
        )

        video_url = self._atlas.run(
            "model/generateVideo", body, label="Seedance2-Loop",
        )[0]

        # Download the looping MP4 to a temp file.
        tmp_dir = tempfile.mkdtemp(prefix="seedance2-loop-")
        raw_path = os.path.join(tmp_dir, "drone-loop-raw.mp4")
        self._atlas.download(video_url, raw_path)
        size_mb = os.path.getsize(raw_path) / 1024 / 1024
        print(f"[Seedance2-Loop] Downloaded {size_mb:.1f} MB → {raw_path}", flush=True)

        # Post-process: crossfade the last second into a copy of the first
        # second. Insurance against residual frame drift — Seedance i2v lands
        # ~85% close to last_image but rarely pixel-identical. The crossfade
        # masks the remaining ~15% so a YouTube auto-loop has no perceived
        # jump at the 12s → 0s seam.
        polished_path = os.path.join(tmp_dir, "drone-loop.mp4")
        self._apply_loop_crossfade(raw_path, polished_path, fade_duration=1.0)
        return polished_path

    @staticmethod
    def _apply_loop_crossfade(input_path: str, output_path: str, fade_duration: float = 1.0) -> None:
        """Render a seamless-loop version of `input_path` by crossfading the
        last `fade_duration` seconds into a copy of the first `fade_duration`
        seconds. Output length equals input length — the crossfade replaces
        the tail rather than extending it.

        Both video (xfade=fade) and audio (acrossfade) are blended so neither
        ticks at the loop point.
        """
        # Probe input duration so the xfade offset is correct regardless of
        # whether Seedance returned exactly 12.0s (often it's 11.97-12.04s).
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            check=True, capture_output=True, text=True,
        )
        try:
            duration = float(probe.stdout.strip())
        except ValueError:
            duration = 12.0
        body_len = max(0.1, duration - fade_duration)
        xfade_offset = body_len  # xfade starts at `offset` seconds into the first input
        print(f"[Seedance2-Loop] Crossfading last {fade_duration:.1f}s into first {fade_duration:.1f}s "
              f"(input duration {duration:.2f}s, body kept {body_len:.2f}s)", flush=True)

        # filter_complex graph:
        #   v0 = full input video
        #   head_v = first `fade_duration` seconds of video
        #   v0 + head_v xfade @ offset=body_len → final video (input duration)
        #   same for audio with acrossfade
        filter_complex = (
            f"[0:v]trim=duration={fade_duration},setpts=PTS-STARTPTS[head_v];"
            f"[0:v]setpts=PTS-STARTPTS[body_v];"
            f"[body_v][head_v]xfade=transition=fade:duration={fade_duration}:offset={xfade_offset}[v_out];"
            f"[0:a]atrim=duration={fade_duration},asetpts=PTS-STARTPTS[head_a];"
            f"[0:a]asetpts=PTS-STARTPTS[body_a];"
            f"[body_a][head_a]acrossfade=d={fade_duration}[a_out]"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", input_path,
                "-filter_complex", filter_complex,
                "-map", "[v_out]", "-map", "[a_out]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                output_path,
            ],
            check=True,
        )
        out_size = os.path.getsize(output_path) / 1024 / 1024
        print(f"[Seedance2-Loop] Crossfade complete → {output_path} ({out_size:.1f} MB)", flush=True)


class AtlasSeedance2T2VProducer:
    """Single-clip text-to-video via Seedance 2.0 with native audio.

    No image anchoring, no loop constraint, no post-processing. Used by
    preset-8 (Cinematic Drone) for dynamic chase / wildlife / impossible-vista
    / human-reaction shots that end mid-action.

    Submit one Seedance 2.0 t2v request → poll → download MP4 → return path.
    Seedance generates both video and matching ambient + subject audio in the
    same call (generate_audio=True), so the orchestrator skips the audio mixer.
    """

    def __init__(self, client: AtlasClient | None = None):
        self._atlas = client or AtlasClient()

    def produce(self, prompt: str, params: dict) -> str:
        body = {
            "model": ATLAS_VIDEO_MODEL_SEEDANCE_2_T2V,
            "prompt": prompt,
            "duration": params.get("duration", 12),
            "resolution": params.get("resolution", "720p-SR"),
            "ratio": params.get("ratio", "9:16"),
            "generate_audio": params.get("generate_audio", True),
            "watermark": params.get("watermark", False),
            "return_last_frame": False,
        }
        print(
            f"[Seedance2-T2V] Submitting: duration={body['duration']}s "
            f"resolution={body['resolution']} ratio={body['ratio']} "
            f"audio={body['generate_audio']}",
            flush=True,
        )

        video_url = self._atlas.run(
            "model/generateVideo", body, label="Seedance2-T2V",
        )[0]

        tmp_dir = tempfile.mkdtemp(prefix="seedance2-t2v-")
        out_path = os.path.join(tmp_dir, "drone.mp4")
        self._atlas.download(video_url, out_path)
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"[Seedance2-T2V] Downloaded {size_mb:.1f} MB → {out_path}", flush=True)
        return out_path


class AtlasSeedance1_5T2VFastProducer:
    """Single-clip text-to-video via Seedance 1.5 Pro Fast — cheap variant.

    ~12x cheaper than Seedance 2.0 (~$0.018/sec vs ~$0.21/sec) but no native
    audio generation and max duration is 10s. Used by preset-8 when
    seedance2.model_variant == "1.5-fast". Output clips are silent — bolt on
    ambient audio downstream if needed.

    Body schema differs from Seedance 2.0:
      - `aspect_ratio` (underscored) not `ratio`
      - plain `720p` / `1080p`, no `720p-SR`
      - no `generate_audio`, `watermark`, or `return_last_frame` fields
    """

    def __init__(self, client: AtlasClient | None = None):
        self._atlas = client or AtlasClient()

    def produce(self, prompt: str, params: dict) -> str:
        body = {
            "model": ATLAS_VIDEO_MODEL_SEEDANCE_1_5_T2V_FAST,
            "prompt": prompt,
            "duration": min(params.get("duration", 10), 10),  # 1.5-fast hard cap
            "resolution": params.get("resolution", "720p"),
            "aspect_ratio": params.get("ratio", "9:16"),
        }
        print(
            f"[Seedance1.5-Fast] Submitting: duration={body['duration']}s "
            f"resolution={body['resolution']} aspect_ratio={body['aspect_ratio']}",
            flush=True,
        )

        video_url = self._atlas.run(
            "model/generateVideo", body, label="Seedance1.5-Fast",
        )[0]

        tmp_dir = tempfile.mkdtemp(prefix="seedance1.5-fast-")
        out_path = os.path.join(tmp_dir, "drone.mp4")
        self._atlas.download(video_url, out_path)
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"[Seedance1.5-Fast] Downloaded {size_mb:.1f} MB → {out_path}", flush=True)
        return out_path
