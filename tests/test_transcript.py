"""Tests for transcript management functionality."""

import json
from pathlib import Path

import pytest

from audioscribe.transcript import TranscriptManager


@pytest.fixture
def transcript_manager(tmp_path):
    """Create a TranscriptManager instance with a temporary directory."""
    return TranscriptManager(tmp_path)


def test_get_base_filename(transcript_manager):
    """Test _get_base_filename method with various filename patterns."""
    # Test filename with single extension
    assert transcript_manager._get_base_filename(Path("simple.wav")) == "simple"

    # Test filename with period in name
    assert transcript_manager._get_base_filename(Path("File 09 (1.33).wav")) == "File 09 (1.33)"

    # Test filename with multiple periods
    assert transcript_manager._get_base_filename(Path("file.name.with.periods.mp3")) == "file.name.with.periods"

    # Test filename with no extension
    assert transcript_manager._get_base_filename(Path("no_extension")) == "no_extension"


def test_save_transcript_with_periods_in_filename(transcript_manager):
    """Test saving transcripts for files with periods in their names."""
    original_file = Path("File 09 (1.33).wav")
    text = "Test transcript content"
    metadata = {"test": "metadata"}

    txt_path, json_path = transcript_manager.save_transcript(text, metadata, original_file)

    # Verify paths are correct
    assert txt_path.name == "File 09 (1.33).txt"
    assert json_path.name == "File 09 (1.33).json"

    # Verify file contents
    assert txt_path.read_text() == text
    assert json.loads(json_path.read_text()) == metadata


def test_check_existing_transcripts_with_periods(transcript_manager):
    """Test checking existing transcripts for files with periods in their names."""
    # Create test files
    base_name = "File 09 (1.33)"
    txt_path = transcript_manager.transcript_dir / f"{base_name}.txt"
    json_path = transcript_manager.transcript_dir / f"{base_name}.json"

    txt_path.write_text("Test content")
    json_path.write_text("{}")

    # Check with original audio file path
    audio_file = Path(f"{base_name}.wav")
    assert transcript_manager.check_existing_transcripts(audio_file) is True


def test_check_existing_transcripts_missing_files(transcript_manager):
    """Test checking non-existent transcripts."""
    audio_file = Path("File 09 (1.33).wav")
    assert transcript_manager.check_existing_transcripts(audio_file) is False


def test_check_existing_transcripts_empty_files(transcript_manager):
    """Test checking existing but empty transcript files."""
    # Create empty test files
    base_name = "File 09 (1.33)"
    txt_path = transcript_manager.transcript_dir / f"{base_name}.txt"
    json_path = transcript_manager.transcript_dir / f"{base_name}.json"

    txt_path.touch()
    json_path.touch()

    # Check with original audio file path
    audio_file = Path(f"{base_name}.wav")
    assert transcript_manager.check_existing_transcripts(audio_file) is False


def test_save_transcript_verification(transcript_manager):
    """Test verification of saved transcript files."""
    original_file = Path("test.wav")
    text = "Test content"
    metadata = {"test": "metadata"}

    # Test successful save
    txt_path, json_path = transcript_manager.save_transcript(text, metadata, original_file)
    assert txt_path.exists()
    assert json_path.exists()
    assert txt_path.read_text() == text
    assert json.loads(json_path.read_text()) == metadata

    # Test empty content handling
    with pytest.raises(RuntimeError, match="Failed to save or verify"):
        transcript_manager.save_transcript("", metadata, original_file)


def test_merge_transcripts_with_missing_parts(transcript_manager):
    """Test merge behavior when some part files are missing."""
    # Create test files with gaps in part numbers
    base_name = "test_audio"
    parts = [0, 2, 4]  # Missing parts 1 and 3

    for part in parts:
        part_file = transcript_manager.transcript_dir / f"{base_name}_part{part:03d}.txt"
        part_file.write_text(f"Content part {part}")

    # Trigger merge
    transcript_manager.merge_transcripts()

    # Check merged file
    merged_file = transcript_manager.transcript_dir / f"{base_name}.txt"
    assert merged_file.exists()
    content = merged_file.read_text()

    # Verify only existing parts were merged
    for part in parts:
        assert f"Content part {part}" in content


def test_merge_transcripts_with_duplicate_parts(transcript_manager):
    """Test merge behavior with duplicate part numbers (which shouldn't happen in practice)."""
    base_name = "test_audio"

    # Create original part file
    part_file = transcript_manager.transcript_dir / f"{base_name}_part000.txt"
    part_file.write_text("Original content")

    # Create duplicate with different content (in a subdirectory)
    subdir = transcript_manager.transcript_dir / "subdir"
    subdir.mkdir()
    duplicate = subdir / f"{base_name}_part000.txt"
    duplicate.write_text("Duplicate content")

    # Trigger merge
    transcript_manager.merge_transcripts()

    # Check merged file
    merged_file = transcript_manager.transcript_dir / f"{base_name}.txt"
    assert merged_file.exists()
    content = merged_file.read_text()

    # Verify only one version was included
    assert content.count("content") == 1


def test_merge_transcripts_with_non_sequential_parts(transcript_manager):
    """Test merge behavior with non-sequential part numbers."""
    base_name = "test_audio"
    parts = [5, 2, 8, 1]  # Non-sequential parts

    for part in parts:
        part_file = transcript_manager.transcript_dir / f"{base_name}_part{part:03d}.txt"
        part_file.write_text(f"Content part {part}")

    # Trigger merge
    transcript_manager.merge_transcripts()

    # Check merged file
    merged_file = transcript_manager.transcript_dir / f"{base_name}.txt"
    assert merged_file.exists()
    content = merged_file.read_text().split("\n\n")

    # Verify parts were merged in correct order
    sorted_parts = sorted(parts)
    for i, part in enumerate(sorted_parts):
        assert content[i] == f"Content part {part}"


def test_merge_transcripts_with_mixed_clean_and_raw(transcript_manager):
    """Test merging when some parts have clean versions and others don't."""
    base_name = "test_audio"

    # Create mix of clean and raw transcripts
    parts = {
        0: ("Raw content 0", True),  # (content, has_clean)
        1: ("Raw content 1", False),
        2: ("Raw content 2", True),
    }

    for part, (content, has_clean) in parts.items():
        # Create raw version
        part_file = transcript_manager.transcript_dir / f"{base_name}_part{part:03d}.txt"
        part_file.write_text(content)

        # Create clean version for some parts
        if has_clean:
            clean_file = transcript_manager.transcript_dir / f"{base_name}_part{part:03d}.clean.txt"
            clean_file.write_text(f"Clean {content}")

    # Trigger merge
    transcript_manager.merge_transcripts()

    # Check merged files
    raw_merged = transcript_manager.transcript_dir / f"{base_name}.txt"
    clean_merged = transcript_manager.transcript_dir / f"{base_name}.clean.txt"

    assert raw_merged.exists()
    assert clean_merged.exists()

    # Verify raw content
    raw_content = raw_merged.read_text()
    for part in range(3):
        assert f"Raw content {part}" in raw_content

    # Verify clean content
    clean_content = clean_merged.read_text()
    for part, (_, has_clean) in parts.items():
        if has_clean:
            assert f"Clean Raw content {part}" in clean_content


def test_save_transcript_with_special_characters(transcript_manager):
    """Test saving transcripts with special characters in content."""
    original_file = Path("test.wav")
    special_chars = "Special characters: áéíóú ñ 你好 🌟 \n\t\"'[]{}!@#$%^&*()"
    metadata = {"test": "metadata"}

    txt_path, json_path = transcript_manager.save_transcript(special_chars, metadata, original_file)

    # Verify content was saved and loaded correctly
    assert txt_path.read_text() == special_chars
    assert json.loads(json_path.read_text()) == metadata
