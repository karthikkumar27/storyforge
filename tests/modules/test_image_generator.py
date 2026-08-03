# tests/modules/test_image_generator.py
import pytest

from config import ATLAS_IMAGE_EDIT_MODEL, ATLAS_IMAGE_MODEL
from modules.atlas_client import AtlasContentFilterError, AtlasTaskFailed
from modules.image_generator import (
    EDIT_POLL_INTERVAL,
    IMAGE_POLL_INTERVAL,
    MAX_RETRIES,
    SAFE_PREFIX,
    AtlasImageGenerator,
)
from tests.support import StubAtlasClient


def test_generate_returns_the_output_url():
    client = StubAtlasClient(outputs=["https://cdn/ref.png"])

    assert AtlasImageGenerator(client).generate("a lone traveller") == "https://cdn/ref.png"


def test_generate_sends_the_prompt_unchanged_on_the_first_attempt():
    client = StubAtlasClient()

    AtlasImageGenerator(client).generate("a lone traveller")

    body = client.calls[0]["body"]
    assert body["prompt"] == "a lone traveller"
    assert body["model"] == ATLAS_IMAGE_MODEL
    assert (body["width"], body["height"]) == (768, 1344)
    assert client.calls[0]["poll_interval"] == IMAGE_POLL_INTERVAL


def test_generate_accepts_a_model_override():
    """preset-8 uses a more permissive model because GPT Image 2 refuses
    'drone' prompts."""
    client = StubAtlasClient()

    AtlasImageGenerator(client).generate("aerial vista", model="bytedance/seedream-v4.5")

    assert client.calls[0]["body"]["model"] == "bytedance/seedream-v4.5"


def test_generate_softens_the_prompt_after_a_content_filter_refusal():
    client = StubAtlasClient(
        outputs=["https://cdn/ref.png"],
        errors=[AtlasContentFilterError("refused"), None],
    )

    url = AtlasImageGenerator(client).generate("a lone traveller")

    assert url == "https://cdn/ref.png"
    assert client.calls[0]["body"]["prompt"] == "a lone traveller"
    assert client.calls[1]["body"]["prompt"] == f"{SAFE_PREFIX}a lone traveller"


def test_generate_retries_other_failures_too():
    client = StubAtlasClient(errors=[AtlasTaskFailed("model blew up"), None])

    AtlasImageGenerator(client).generate("x")

    assert len(client.calls) == 2


def test_generate_gives_up_after_the_retry_budget():
    client = StubAtlasClient(
        errors=[AtlasContentFilterError("refused")] * MAX_RETRIES,
    )

    with pytest.raises(AtlasContentFilterError):
        AtlasImageGenerator(client).generate("a lone traveller")

    assert len(client.calls) == MAX_RETRIES


def test_edit_image_anchors_to_the_base_image():
    client = StubAtlasClient(outputs=["https://cdn/shot3.png"])

    url = AtlasImageGenerator(client).edit_image("https://cdn/alan.png", "he turns")

    assert url == "https://cdn/shot3.png"
    body = client.calls[0]["body"]
    assert body["image"] == "https://cdn/alan.png"
    assert body["prompt"] == "he turns"
    assert body["model"] == ATLAS_IMAGE_EDIT_MODEL
    assert client.calls[0]["poll_interval"] == EDIT_POLL_INTERVAL


def test_edit_image_retries_then_gives_up():
    client = StubAtlasClient(errors=[AtlasTaskFailed("gateway")] * MAX_RETRIES)

    with pytest.raises(AtlasTaskFailed):
        AtlasImageGenerator(client).edit_image("https://cdn/alan.png", "he turns")

    assert len(client.calls) == MAX_RETRIES


def test_edit_image_does_not_prepend_the_safe_prefix():
    """SAFE_PREFIX says 'no humans' -- correct for a scene reference, wrong for
    a storyboard frame whose whole job is to keep the character in shot."""
    client = StubAtlasClient(errors=[AtlasTaskFailed("blip"), None])

    AtlasImageGenerator(client).edit_image("https://cdn/alan.png", "he turns")

    assert all(SAFE_PREFIX not in call["body"]["prompt"] for call in client.calls)


def test_edit_accepts_a_list_of_base_images_in_order():
    """Chained storyboards pass [locked_reference, previous_frame]. Order is the
    identity-authority signal, so it must survive to the request body."""
    from modules.image_generator import AtlasImageGenerator
    from tests.support import StubAtlasClient
    client = StubAtlasClient(outputs=["https://cdn/sb.png"])

    AtlasImageGenerator(client).edit_image(
        ["https://cdn/ref.png", "data:image/png;base64,AAAA"], "a rooftop"
    )

    assert client.calls[0]["body"]["image"] == [
        "https://cdn/ref.png", "data:image/png;base64,AAAA",
    ]


def test_edit_still_accepts_a_single_base_image():
    from modules.image_generator import AtlasImageGenerator
    from tests.support import StubAtlasClient
    client = StubAtlasClient(outputs=["https://cdn/sb.png"])

    AtlasImageGenerator(client).edit_image("https://cdn/ref.png", "a rooftop")

    assert client.calls[0]["body"]["image"] == "https://cdn/ref.png"


def test_edit_logs_a_readable_base_for_a_data_uri():
    """A base64 data URI is ~300KB; logging it raw floods the pipeline output."""
    from modules.image_generator import AtlasImageGenerator
    from tests.support import StubAtlasClient
    import io, contextlib
    client = StubAtlasClient(outputs=["https://cdn/sb.png"])

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        AtlasImageGenerator(client).edit_image(
            ["https://cdn/ref.png", "data:image/png;base64," + "A" * 5000], "x"
        )

    assert len(buffer.getvalue()) < 2000
