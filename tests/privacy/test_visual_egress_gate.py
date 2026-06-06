"""Cap E acceptance tests — outbound visual/multimodal egress for image-gen.

Covers the acceptance criterion from
``docs/exec-plans/active/nanobot-rebase.md`` Cap E:

  *reference image redacted + prompt placeholdered before bytes leave;
  fail-closed omits the image.*

The gate is a privacy-owned wrapper around an image-gen provider's ``generate``
call. These tests drive the wrapper directly with a fake inner provider and
patch the two pipeline entry points the gate uses (``process_visual_blocks`` for
reference images, ``sanitize_input_with_detection`` for the prompt) in the
gate's own module namespace — the documented redaction-test pattern that
overrides the autouse no-op fixture.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from cloakbot.privacy import visual_egress_gate as gate_mod
from cloakbot.privacy.visual_egress_gate import (
    VisualEgressGatedImageProvider,
    wrap_image_provider_with_visual_egress_gate,
)
from cloakbot.privacy.visual_redaction import VisualBlocksResult

# A minimal valid 1x1 PNG.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x04\x00\x00\x00\xb5\x1c\x0c\x02"
    b"\x00\x00\x00\x0bIDATx\xdacd\xfc\xff\x1f\x00\x03\x03"
    b"\x02\x00\xef\xbf\xa7\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)
# Distinct bytes so we can prove the *redacted* (not original) image was sent.
_REDACTED_PNG_BYTES = _PNG_BYTES[:-4] + b"REDX"
_REDACTED_DATA_URL = (
    "data:image/png;base64," + base64.b64encode(_REDACTED_PNG_BYTES).decode("ascii")
)

# The raw value a caller might embed in the prompt; never allowed out raw.
_RAW_NAME = "John Q. Public"
_PLACEHOLDER_PROMPT = "make a poster for <<PERSON_1>>"


class _FakeInnerProvider:
    """Records exactly what the gate forwards to the remote endpoint."""

    provider_name = "fake"

    def __init__(self, **kwargs: Any) -> None:
        self.init_kwargs = kwargs
        self.calls: list[dict[str, Any]] = []
        self.some_attr = "delegated"

    async def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"images": ["data:image/png;base64,GENERATED"], "content": ""}


def _vault_workspace(tmp_path) -> None:
    from cloakbot.privacy.core.state.vault import set_vault_workspace

    set_vault_workspace(tmp_path)


@pytest.mark.asyncio
async def test_reference_image_redacted_and_prompt_placeholdered(tmp_path, monkeypatch):
    """The redacted reference + placeholdered prompt reach the remote provider."""
    _vault_workspace(tmp_path)

    async def _fake_process(blocks, **kwargs):
        # Stand in for the real OCR/redaction pipeline: return a *redacted*
        # image_url block (different bytes from the original). The pipeline
        # stamps a visual_privacy record carrying the redaction-box count; a
        # confidently-redacted block (>=1 box) is the only thing M2 forwards.
        return VisualBlocksResult(
            redacted_blocks=[
                {
                    "type": "image_url",
                    "image_url": {"url": _REDACTED_DATA_URL},
                    "_meta": {"visual_privacy": {"redactionBoxes": 2, "status": "redacted"}},
                },
                {"type": "text", "text": "[Image redaction map — <<PERSON_1>> ...]"},
            ],
            sanitized_text="",
            modified=True,
        )

    async def _fake_sanitize(text, session_key, *, fail_open=True, turn_id=None):
        # Prove the raw value never survives: replace it with a placeholder.
        assert _RAW_NAME in text
        return _PLACEHOLDER_PROMPT, True, [], None

    monkeypatch.setattr(gate_mod, "process_visual_blocks", _fake_process)
    monkeypatch.setattr(gate_mod, "sanitize_input_with_detection", _fake_sanitize)

    inner = _FakeInnerProvider()
    gate = VisualEgressGatedImageProvider(inner)

    ref = tmp_path / "ref.png"
    ref.write_bytes(_PNG_BYTES)

    await gate.generate(
        prompt=f"make a poster for {_RAW_NAME}",
        model="some/image-model",
        reference_images=[str(ref)],
        aspect_ratio="1:1",
        image_size="1K",
    )

    assert len(inner.calls) == 1
    call = inner.calls[0]

    # 1. Prompt is placeholdered — the raw name never reaches the provider.
    assert call["prompt"] == _PLACEHOLDER_PROMPT
    assert _RAW_NAME not in call["prompt"]

    # 2. Exactly one redacted reference image was forwarded, on disk in the vault.
    forwarded = call["reference_images"]
    assert forwarded is not None and len(forwarded) == 1
    forwarded_bytes = open(forwarded[0], "rb").read()
    # The redacted bytes (not the original) are what left the host.
    assert forwarded_bytes == _REDACTED_PNG_BYTES
    assert forwarded_bytes != _PNG_BYTES

    # Passthrough args preserved.
    assert call["model"] == "some/image-model"
    assert call["aspect_ratio"] == "1:1"
    assert call["image_size"] == "1K"


@pytest.mark.asyncio
async def test_fail_closed_omits_unredactable_reference_image(tmp_path, monkeypatch):
    """When the pipeline cannot redact an image it is omitted, never sent raw."""
    _vault_workspace(tmp_path)

    async def _fail_closed_process(blocks, **kwargs):
        # Fail-closed: the pipeline replaced the image with a text placeholder
        # (no forwardable image_url block remains).
        return VisualBlocksResult(
            redacted_blocks=[
                {"type": "text", "text": "[visual content omitted; fail-closed]"},
            ],
            sanitized_text="",
            modified=True,
        )

    async def _passthrough_sanitize(text, session_key, *, fail_open=True, turn_id=None):
        return text, False, [], None

    monkeypatch.setattr(gate_mod, "process_visual_blocks", _fail_closed_process)
    monkeypatch.setattr(gate_mod, "sanitize_input_with_detection", _passthrough_sanitize)

    inner = _FakeInnerProvider()
    gate = VisualEgressGatedImageProvider(inner)

    ref = tmp_path / "secret_invoice.png"
    ref.write_bytes(_PNG_BYTES)

    await gate.generate(
        prompt="enhance this",
        model="some/image-model",
        reference_images=[str(ref)],
    )

    assert len(inner.calls) == 1
    # No reference image survived — the unredactable image was omitted entirely.
    assert inner.calls[0]["reference_images"] is None


@pytest.mark.asyncio
async def test_undecodable_reference_path_is_omitted(tmp_path, monkeypatch):
    """A reference path that is not a readable image is dropped (fail-closed)."""
    _vault_workspace(tmp_path)

    seen_blocks: list[Any] = []

    async def _record_process(blocks, **kwargs):
        seen_blocks.append(blocks)
        return VisualBlocksResult(redacted_blocks=list(blocks), sanitized_text="", modified=False)

    async def _passthrough_sanitize(text, session_key, *, fail_open=True, turn_id=None):
        return text, False, [], None

    monkeypatch.setattr(gate_mod, "process_visual_blocks", _record_process)
    monkeypatch.setattr(gate_mod, "sanitize_input_with_detection", _passthrough_sanitize)

    inner = _FakeInnerProvider()
    gate = VisualEgressGatedImageProvider(inner)

    # A path that exists but is not an image.
    not_image = tmp_path / "notes.txt"
    not_image.write_text("totally not an image")

    await gate.generate(
        prompt="draw",
        model="some/image-model",
        reference_images=[str(not_image)],
    )

    # The undecodable reference was filtered before redaction even ran, so the
    # pipeline saw no image blocks and nothing was forwarded.
    assert seen_blocks == [] or all(not b for b in seen_blocks)
    assert inner.calls[0]["reference_images"] is None


@pytest.mark.asyncio
async def test_no_reference_images_only_sanitizes_prompt(tmp_path, monkeypatch):
    """Text-only generation still placeholders the prompt; image path untouched."""
    _vault_workspace(tmp_path)

    called = {"process": False}

    async def _process(blocks, **kwargs):
        called["process"] = True
        return VisualBlocksResult(redacted_blocks=list(blocks), sanitized_text="", modified=False)

    async def _sanitize(text, session_key, *, fail_open=True, turn_id=None):
        return "<<PERSON_1>> portrait", True, [], None

    monkeypatch.setattr(gate_mod, "process_visual_blocks", _process)
    monkeypatch.setattr(gate_mod, "sanitize_input_with_detection", _sanitize)

    inner = _FakeInnerProvider()
    gate = VisualEgressGatedImageProvider(inner)

    await gate.generate(prompt="Alice portrait", model="m", reference_images=None)

    assert called["process"] is False  # no image path => pipeline not invoked
    assert inner.calls[0]["prompt"] == "<<PERSON_1>> portrait"
    assert inner.calls[0]["reference_images"] is None


@pytest.mark.asyncio
async def test_prompt_fail_closed_blocks_image_gen_when_detector_down(tmp_path, monkeypatch):
    """H3: a detector outage blocks the image-gen call — no raw prompt leaves.

    The prompt goes to a REMOTE endpoint, so on detector unavailability the gate
    must refuse to forward an unsanitized prompt. ``generate`` raises
    ImageGenerationError and the inner provider is never called.
    """
    from cloakbot.providers.image_generation import ImageGenerationError

    _vault_workspace(tmp_path)

    async def _detector_down(text, session_key, *, fail_open=False, turn_id=None):
        # Mirror the real detector's fail-CLOSED contract: it raises when down.
        assert fail_open is False
        raise RuntimeError("local LLM detector unavailable")

    async def _never_called_process(blocks, **kwargs):  # pragma: no cover - guard
        raise AssertionError("redaction must not run once the prompt is blocked")

    monkeypatch.setattr(gate_mod, "sanitize_input_with_detection", _detector_down)
    monkeypatch.setattr(gate_mod, "process_visual_blocks", _never_called_process)

    inner = _FakeInnerProvider()
    gate = VisualEgressGatedImageProvider(inner)

    with pytest.raises(ImageGenerationError):
        await gate.generate(
            prompt="make a poster for John Q. Public at 12 Acacia Ave",
            model="some/image-model",
        )

    # The raw prompt never reached the remote provider.
    assert inner.calls == []


@pytest.mark.asyncio
async def test_reference_with_zero_redaction_regions_is_omitted(tmp_path, monkeypatch):
    """M2: a reference image with no confident redaction regions is omitted.

    The shared OCR pipeline forwards the ORIGINAL bytes for an image with no OCR
    text and no detector items (redaction_boxes == 0). For the image-gen egress
    path we fail-closed-by-default and drop it rather than ship it raw.
    """
    _vault_workspace(tmp_path)

    async def _no_region_process(blocks, **kwargs):
        # Pipeline produced a "redacted" image_url block but drew ZERO boxes —
        # i.e. these are effectively the original bytes.
        return VisualBlocksResult(
            redacted_blocks=[
                {
                    "type": "image_url",
                    "image_url": {"url": _REDACTED_DATA_URL},
                    "_meta": {"visual_privacy": {"redactionBoxes": 0, "status": "redacted"}},
                },
            ],
            sanitized_text="",
            modified=False,
        )

    async def _passthrough_sanitize(text, session_key, *, fail_open=False, turn_id=None):
        return text, False, [], None

    monkeypatch.setattr(gate_mod, "process_visual_blocks", _no_region_process)
    monkeypatch.setattr(gate_mod, "sanitize_input_with_detection", _passthrough_sanitize)

    inner = _FakeInnerProvider()
    gate = VisualEgressGatedImageProvider(inner)

    ref = tmp_path / "vacation_photo.png"
    ref.write_bytes(_PNG_BYTES)

    await gate.generate(
        prompt="add a sunset",
        model="some/image-model",
        reference_images=[str(ref)],
    )

    assert len(inner.calls) == 1
    # The zero-region reference was omitted — no original bytes forwarded.
    assert inner.calls[0]["reference_images"] is None


def test_wrap_is_idempotent_and_passthrough_attrs():
    """Double-wrapping is a no-op; attributes delegate to the inner provider."""
    inner = _FakeInnerProvider()
    once = wrap_image_provider_with_visual_egress_gate(inner)
    twice = wrap_image_provider_with_visual_egress_gate(once)

    assert isinstance(once, VisualEgressGatedImageProvider)
    assert twice is once  # idempotent
    # Transparent delegation of unrelated attributes.
    assert once.some_attr == "delegated"
    assert once.provider_name == "fake"
    assert once.inner is inner


def test_wrap_none_returns_none():
    assert wrap_image_provider_with_visual_egress_gate(None) is None


@pytest.mark.asyncio
async def test_tool_provider_client_is_gated(tmp_path, monkeypatch):
    """The image-gen tool installs the Cap E gate at provider-factory time."""
    from cloakbot.agent.tools import image_generation as img_tool_mod
    from cloakbot.agent.tools.image_generation import (
        ImageGenerationTool,
        ImageGenerationToolConfig,
    )
    from cloakbot.config.loader import set_config_path
    from cloakbot.config.schema import ProviderConfig

    set_config_path(tmp_path / "config.json")

    monkeypatch.setattr(
        img_tool_mod,
        "get_image_gen_provider",
        lambda name: _FakeInnerProvider if name == "openrouter" else None,
    )
    tool = ImageGenerationTool(
        workspace=tmp_path,
        config=ImageGenerationToolConfig(enabled=True),
        provider_config=ProviderConfig(api_key="sk-or-test"),
    )

    client = tool._provider_client()
    assert isinstance(client, VisualEgressGatedImageProvider)
