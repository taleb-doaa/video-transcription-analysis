import pytest

from app.services.srt_service import generate_srt


def test_generate_srt_basic_format():
    segments = [
        {"start": 0.5, "end": 5.8, "speaker": None, "text": "Bonjour."},
    ]

    result = generate_srt(segments)

    assert "1\n" in result
    assert "00:00:00,500 --> 00:00:05,800" in result
    assert "Bonjour." in result


def test_generate_srt_includes_speaker_label():
    segments = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_01", "text": "Salut."},
    ]

    result = generate_srt(segments)

    assert "SPEAKER_01: Salut." in result


def test_generate_srt_handles_hour_long_timestamps():
    segments = [
        {"start": 3661.25, "end": 3665.0, "speaker": None, "text": "Une heure plus tard."},
    ]

    result = generate_srt(segments)

    assert "01:01:01,250 --> 01:01:05,000" in result


def test_generate_srt_skips_empty_text_segments():
    segments = [
        {"start": 0.0, "end": 2.0, "speaker": None, "text": "   "},
        {"start": 2.0, "end": 4.0, "speaker": None, "text": "Texte valide."},
    ]

    result = generate_srt(segments)

    assert result.startswith("1\n")
    assert "Texte valide." in result
    assert result.count("-->") == 1


def test_generate_srt_raises_on_empty_transcript():
    with pytest.raises(ValueError, match="empty"):
        generate_srt([])


def test_generate_srt_raises_when_all_segments_are_blank():
    segments = [{"start": 0.0, "end": 2.0, "speaker": None, "text": ""}]

    with pytest.raises(ValueError, match="non-empty"):
        generate_srt(segments)


def test_generate_srt_sequential_numbering():
    segments = [
        {"start": 0.0, "end": 2.0, "speaker": None, "text": "Un."},
        {"start": 2.0, "end": 4.0, "speaker": None, "text": "Deux."},
        {"start": 4.0, "end": 6.0, "speaker": None, "text": "Trois."},
    ]

    result = generate_srt(segments)

    assert "1\n" in result
    assert "\n2\n" in result
    assert "\n3\n" in result