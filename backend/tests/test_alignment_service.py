from app.services.alignment_service import merge_speakers


def test_merge_speakers_assigns_matching_speaker():
    transcript_segments = [
        {"start": 0.0, "end": 5.0, "text": "Bonjour"},
    ]
    diarization_segments = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01"},
    ]

    result = merge_speakers(transcript_segments, diarization_segments)

    assert result[0]["speaker"] == "SPEAKER_01"
    assert result[0]["text"] == "Bonjour"


def test_merge_speakers_picks_speaker_with_largest_overlap():
    transcript_segments = [
        {"start": 4.0, "end": 10.0, "text": "Merci pour votre invitation"},
    ]
    diarization_segments = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01"},
        {"start": 5.0, "end": 12.0, "speaker": "SPEAKER_02"},
    ]

    result = merge_speakers(transcript_segments, diarization_segments)

    # Overlap avec SPEAKER_01: [4,5] = 1s
    # Overlap avec SPEAKER_02: [5,10] = 5s -> doit gagner
    assert result[0]["speaker"] == "SPEAKER_02"


def test_merge_speakers_returns_none_when_no_overlap():
    transcript_segments = [
        {"start": 20.0, "end": 25.0, "text": "Segment isolé"},
    ]
    diarization_segments = [
        {"start": 0.0, "end": 5.0, "speaker": "SPEAKER_01"},
    ]

    result = merge_speakers(transcript_segments, diarization_segments)

    assert result[0]["speaker"] is None


def test_merge_speakers_handles_empty_diarization():
    transcript_segments = [
        {"start": 0.0, "end": 5.0, "text": "Test"},
    ]

    result = merge_speakers(transcript_segments, [])

    assert result[0]["speaker"] is None
    assert len(result) == 1


def test_merge_speakers_handles_multiple_transcript_segments():
    transcript_segments = [
        {"start": 0.0, "end": 3.0, "text": "Un"},
        {"start": 3.0, "end": 6.0, "text": "Deux"},
    ]
    diarization_segments = [
        {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_01"},
        {"start": 3.0, "end": 6.0, "speaker": "SPEAKER_02"},
    ]

    result = merge_speakers(transcript_segments, diarization_segments)

    assert result[0]["speaker"] == "SPEAKER_01"
    assert result[1]["speaker"] == "SPEAKER_02"