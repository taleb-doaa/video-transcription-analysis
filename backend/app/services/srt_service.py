from typing import Any


def _format_srt_timestamp(seconds: float) -> str:
    """
    Convert a float number of seconds into the SRT timestamp format:
    HH:MM:SS,mmm (comma as decimal separator, per the SRT spec).
    """
    if seconds < 0:
        seconds = 0

    total_ms = round(seconds * 1000)

    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, ms = divmod(remainder_ms, 1_000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def generate_srt(segments: list[dict[str, Any]]) -> str:
    """
    Convert transcript segments (start, end, text, optional speaker)
    into a standard SRT subtitle file content.

    Segments with empty/missing text are skipped rather than producing
    blank subtitle blocks. The speaker label, when present, is
    prefixed to the subtitle text (e.g. "SPEAKER_01: Bonjour").
    """
    if not segments:
        raise ValueError("Cannot generate SRT: transcript is empty.")

    blocks: list[str] = []
    index = 1

    for segment in segments:
        text = (segment.get("text") or "").strip()

        if not text:
            continue

        speaker = segment.get("speaker")
        display_text = f"{speaker}: {text}" if speaker else text

        start_ts = _format_srt_timestamp(float(segment["start"]))
        end_ts = _format_srt_timestamp(float(segment["end"]))

        blocks.append(f"{index}\n{start_ts} --> {end_ts}\n{display_text}\n")
        index += 1

    if not blocks:
        raise ValueError("Cannot generate SRT: no non-empty segments.")

    return "\n".join(blocks)