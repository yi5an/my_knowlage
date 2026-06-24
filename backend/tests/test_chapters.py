"""Tests for chapter parsing from YouTube video descriptions."""

from app.services.youtube.chapters import parse_chapters, parse_time_to_seconds, seconds_to_str


def test_parse_time_formats() -> None:
    assert parse_time_to_seconds("0:00") == 0
    assert parse_time_to_seconds("5:30") == 330
    assert parse_time_to_seconds("1:02:15") == 3735
    assert parse_time_to_seconds("12:34.500") == 754


def test_parse_time_invalid_minutes() -> None:
    import pytest

    with pytest.raises(ValueError):
        parse_time_to_seconds("1:99")
    with pytest.raises(ValueError):
        parse_time_to_seconds("1:02:99")


def test_seconds_to_str() -> None:
    assert seconds_to_str(0) == "00:00"
    assert seconds_to_str(330) == "05:30"
    assert seconds_to_str(3735) == "1:02:15"


def test_parse_chapters_from_description() -> None:
    description = (
        "In this video we explore GPT-5.\n\n"
        "0:00 Intro\n"
        "5:30 Core findings\n"
        "12:45 Pricing changes\n"
        "1:02:15 Live demo\n\n"
        "Follow me on Twitter."
    )
    chapters = parse_chapters(description)
    assert [c.start_sec for c in chapters] == [0, 330, 765, 3735]
    assert chapters[1].title == "Core findings"
    assert chapters[1].start_str == "05:30"
    assert chapters[-1].start_str == "1:02:15"


def test_parse_chapters_empty_when_none() -> None:
    assert parse_chapters(None) == []
    assert parse_chapters("") == []
    assert parse_chapters("Just a plain description with no timestamps.") == []


def test_parse_chapters_requires_at_least_two() -> None:
    # A single 0:00 line is not a chapter list.
    assert parse_chapters("0:00 Intro\nSome other text.") == []


def test_parse_chapters_requires_strictly_increasing() -> None:
    bad = "0:00 Intro\n5:30 Middle\n5:00 Out of order"
    assert parse_chapters(bad) == []


def test_parse_chapters_handles_missing_title() -> None:
    description = "0:00\n5:30 Real content"
    chapters = parse_chapters(description)
    assert len(chapters) == 2
    # Fallback title uses the timestamp string when blank.
    assert chapters[0].title == "00:00"
