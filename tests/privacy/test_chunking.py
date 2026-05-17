"""Tests for the content-type sniffer + chunkers."""

from __future__ import annotations

import json

import pytest

from cloakbot.privacy.core.detection.chunking import (
    DEFAULT_MAX_CHARS,
    ContentType,
    HtmlChunker,
    JsonChunker,
    MarkdownChunker,
    PlainTextChunker,
    get_chunker,
    sniff_content_type,
)

# ---------------------------------------------------------------------------
# Sniffer
# ---------------------------------------------------------------------------


def test_sniff_returns_json_for_parseable_object() -> None:
    assert sniff_content_type('{"user": {"email": "a@b.com"}}') is ContentType.JSON


def test_sniff_returns_json_for_already_parsed_dict() -> None:
    assert sniff_content_type({"a": 1}) is ContentType.JSON


def test_sniff_returns_html_when_payload_starts_with_a_tag() -> None:
    assert sniff_content_type("<html><body>Hi</body></html>") is ContentType.HTML


def test_sniff_returns_markdown_for_heading_prefix() -> None:
    assert sniff_content_type("# Title\n\nbody") is ContentType.MARKDOWN


def test_sniff_falls_back_to_text_for_jsonish_but_invalid() -> None:
    # Starts with `{` but isn't valid JSON. Falls back to TEXT so the
    # detector doesn't lose the payload to a path-aware chunker that
    # would yield zero useful chunks.
    assert sniff_content_type("{not really json") is ContentType.TEXT


def test_sniff_treats_bytes_as_text() -> None:
    # Image payloads should never enter the text-detection pipeline; if
    # they somehow do (caller bug), the sniffer must produce a safe
    # fallback rather than misclassifying them as JSON.
    assert sniff_content_type(b"\x89PNG\r\n") is ContentType.TEXT


# ---------------------------------------------------------------------------
# Plain-text chunker
# ---------------------------------------------------------------------------


def test_plaintext_chunker_keeps_short_payload_in_one_chunk() -> None:
    chunker = PlainTextChunker()
    chunks = chunker.chunk("hello world")
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].char_span == (0, len("hello world"))


def test_plaintext_chunker_overlap_lets_boundary_entities_survive() -> None:
    chunker = PlainTextChunker()
    # Two big paragraphs separated by a blank line. The first
    # paragraph alone is bigger than the budget, so the chunker has to
    # split inside it; the overlap window means the tail of chunk 0
    # reappears as the head of chunk 1.
    para1 = "A" * (DEFAULT_MAX_CHARS + 50)
    para2 = "B" * 100
    chunks = chunker.chunk(para1 + "\n\n" + para2, overlap_chars=20)
    assert len(chunks) >= 2
    overlap = chunks[0].text[-20:]
    assert chunks[1].text.startswith(overlap)


# ---------------------------------------------------------------------------
# JSON chunker
# ---------------------------------------------------------------------------


def test_json_chunker_flattens_leaves_to_jsonpath_pairs() -> None:
    payload = {
        "users": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob"},
        ],
        "count": 2,
    }
    chunks = JsonChunker().chunk(payload)
    flattened = "\n".join(c.text for c in chunks)
    # Each leaf appears as ``path: value`` so the detector sees enough
    # local context for span-aware PII extraction.
    assert "$.users[0].name: Alice" in flattened
    assert "$.users[0].email: alice@example.com" in flattened
    assert "$.users[1].name: Bob" in flattened
    assert "$.count: 2" in flattened


def test_json_chunker_falls_back_to_text_on_invalid_payload() -> None:
    chunks = JsonChunker().chunk("{not really json")
    # Fallback path yields at least one chunk; we never silently skip
    # detection on malformed JSON.
    assert len(chunks) >= 1
    assert "{not really json" in chunks[0].text


def test_json_chunker_returns_empty_for_all_null_payload() -> None:
    assert JsonChunker().chunk({"a": None, "b": None}) == []


# ---------------------------------------------------------------------------
# HTML chunker
# ---------------------------------------------------------------------------


def test_html_chunker_pulls_meta_mailto_and_visible_text() -> None:
    payload = (
        "<html><head>"
        "<meta name=\"author\" content=\"alice@example.com\"/>"
        "</head><body>"
        "<a href=\"mailto:bob@example.com\">contact</a>"
        "<p>Welcome, Bob!</p>"
        "</body></html>"
    )
    chunks = HtmlChunker().chunk(payload)
    assert len(chunks) >= 1
    body = "\n".join(c.text for c in chunks)
    # All three PII surfaces — meta, attribute-embedded mailto, visible
    # text — must reach the detector.
    assert "alice@example.com" in body
    assert "bob@example.com" in body
    assert "Welcome, Bob!" in body


def test_html_chunker_strips_script_and_style_blocks() -> None:
    payload = (
        "<html><script>var x = 'alice@evil.com';</script>"
        "<style>body { color: red }</style>"
        "<body>Welcome, Bob!</body></html>"
    )
    body = "\n".join(c.text for c in HtmlChunker().chunk(payload))
    # We don't want the detector to chase JavaScript / CSS noise; the
    # values inside script/style blocks should not survive normalisation.
    assert "color: red" not in body
    assert "Welcome, Bob!" in body


# ---------------------------------------------------------------------------
# Markdown chunker
# ---------------------------------------------------------------------------


def test_markdown_chunker_splits_at_headings_and_keeps_section_attached() -> None:
    payload = (
        "# Intro\n\nWelcome.\n\n"
        "## Contact\n\nEmail alice@example.com.\n\n"
        "## Notes\n\nSomething else."
    )
    chunks = MarkdownChunker().chunk(payload, max_chars=50)
    # Each section should be its own chunk because the budget is tiny.
    section_starts = [c.text.lstrip()[:2] for c in chunks]
    assert any(s.startswith("# ") for s in section_starts)
    assert any(s.startswith("##") for s in section_starts)


def test_markdown_chunker_does_not_break_inside_a_fenced_block() -> None:
    # Budget chosen so the heading section containing the fenced block
    # fits as a single chunk — that's the boundary case the chunker is
    # supposed to honour. (An even larger fenced block than the budget
    # has to fall back to plain-text sub-chunking; that's a documented
    # corner case, not the one we're verifying here.)
    fenced = "```\n" + ("x = 1\n" * 5) + "```"
    payload = "## Code\n\n" + fenced + "\n\n## After\n\nBody."
    chunks = MarkdownChunker().chunk(payload, max_chars=500)
    # Locate the chunk containing the open fence; the matching close
    # fence must be in the same chunk so the detector sees the whole
    # block (env vars / API keys in config dumps stay together).
    chunk_with_open = next(c for c in chunks if "```" in c.text)
    assert chunk_with_open.text.count("```") % 2 == 0


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content_type, expected_cls",
    [
        (ContentType.TEXT, PlainTextChunker),
        (ContentType.JSON, JsonChunker),
        (ContentType.HTML, HtmlChunker),
        (ContentType.MARKDOWN, MarkdownChunker),
    ],
)
def test_registry_returns_expected_chunker_per_content_type(content_type, expected_cls) -> None:
    assert isinstance(get_chunker(content_type), expected_cls)


def test_registry_falls_back_to_plaintext_for_unknown_type() -> None:
    # Defensive check: feeding an unexpected enum value should never
    # raise; the detector must keep running on the safe text path.
    class _Fake:
        value = "definitely-not-a-real-type"

    assert isinstance(get_chunker(_Fake()), PlainTextChunker)


# ---------------------------------------------------------------------------
# Sanity: chunkers always preserve the entity payload somewhere
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "chunker, payload",
    [
        (PlainTextChunker(), "Contact alice@example.com today."),
        (JsonChunker(), json.dumps({"email": "alice@example.com"})),
        (HtmlChunker(), "<p>Email alice@example.com</p>"),
        (MarkdownChunker(), "## Contact\n\nalice@example.com"),
    ],
)
def test_email_value_survives_chunking(chunker, payload) -> None:
    text = "\n".join(c.text for c in chunker.chunk(payload))
    assert "alice@example.com" in text
