from unittest.mock import MagicMock, patch

import pytest

from app.services.youtube.normalization import (
    compute_transcript_hash,
    normalize_transcript_text,
)
from app.services.youtube.transcript_provider import (
    FakeTranscriptProvider,
    TranscriptResult,
    TranscriptUnavailableError,
    YouTubeTranscriptApiProvider,
)


def test_transcript_normalization_deterministic() -> None:
    raw_text = "  Hello   world! \n\n Today we are playing   Balatro.   \t\t Let's go!  "
    norm = normalize_transcript_text(raw_text)
    assert norm == "Hello world! Today we are playing Balatro. Let's go!"

    # Determinism
    assert normalize_transcript_text(raw_text) == norm


def test_transcript_normalization_removes_immediate_caption_repeats() -> None:
    raw_text = "hello gamers today we are hello gamers today we are playing elden ring"
    norm = normalize_transcript_text(raw_text)
    assert norm == "hello gamers today we are playing elden ring"


def test_compute_transcript_hash_sha256() -> None:
    text1 = "This is a clean transcript of the video."
    text2 = "This is a clean transcript of the video."
    text3 = "This is a modified transcript of the video."

    hash1 = compute_transcript_hash(text1)
    hash2 = compute_transcript_hash(text2)
    hash3 = compute_transcript_hash(text3)

    assert len(hash1) == 64
    assert hash1 == hash2
    assert hash1 != hash3


@pytest.mark.asyncio
async def test_fake_transcript_provider_success_and_failure() -> None:
    provider = FakeTranscriptProvider(
        canned_transcripts={
            "vid_ok": TranscriptResult(
                text="Speech content",
                language="ru",
                is_generated=True,
                provider="fake-transcript-provider",
                segment_count=10,
            )
        }
    )

    res = await provider.fetch_transcript("vid_ok")
    assert res.text == "Speech content"
    assert res.language == "ru"
    assert res.is_generated is True
    assert res.segment_count == 10

    with pytest.raises(TranscriptUnavailableError):
        await provider.fetch_transcript("vid_nonexistent")


def test_youtube_transcript_api_provider_prefers_manual_over_generated() -> None:
    provider = YouTubeTranscriptApiProvider(preferred_languages=["en", "ru"])

    # Mock transcripts
    manual_mock = MagicMock()
    manual_mock.language_code = "en"
    manual_mock.is_generated = False
    manual_mock.fetch.return_value = [{"text": "Manual subtitle text"}]

    generated_mock = MagicMock()
    generated_mock.language_code = "en"
    generated_mock.is_generated = True
    generated_mock.fetch.return_value = [{"text": "Auto subtitle text"}]

    with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_class:
        instance = mock_api_class.return_value
        instance.list.return_value = [generated_mock, manual_mock]

        result = provider._sync_fetch("test_vid", ["en", "ru"])
        assert result.text == "Manual subtitle text"
        assert result.is_generated is False
        assert result.language == "en"


def test_youtube_transcript_api_provider_falls_back_to_generated() -> None:
    provider = YouTubeTranscriptApiProvider(preferred_languages=["ru", "en"])

    generated_mock = MagicMock()
    generated_mock.language_code = "ru"
    generated_mock.is_generated = True
    generated_mock.fetch.return_value = [{"text": "Автоматические субтитры речи"}]

    with patch("youtube_transcript_api.YouTubeTranscriptApi") as mock_api_class:
        instance = mock_api_class.return_value
        instance.list.return_value = [generated_mock]

        result = provider._sync_fetch("test_vid", ["ru", "en"])
        assert result.text == "Автоматические субтитры речи"
        assert result.is_generated is True
        assert result.language == "ru"
