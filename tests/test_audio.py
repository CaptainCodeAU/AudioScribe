"""Tests for audio processing functionality."""

import json
import os
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audioscribe.audio import AudioProcessor


def test_audio_processor_initialization(audio_config):
    """Test AudioProcessor initialization."""
    processor = AudioProcessor(audio_config)
    assert processor.config == audio_config


def test_ffmpeg_path_modification(audio_config):
    """Test that FFMPEG_PATH is correctly added to system PATH."""
    original_path = os.environ.get("PATH", "")

    processor = AudioProcessor(audio_config)

    # Verify FFMPEG path was added to PATH
    new_path = os.environ["PATH"]
    ffmpeg_dir = os.path.dirname(audio_config.FFMPEG_PATH)
    assert ffmpeg_dir in new_path
    assert new_path.startswith(f"{ffmpeg_dir}:")


@patch("subprocess.run")
def test_get_audio_info_success(mock_run, audio_config, sample_audio_path, mock_audio_info):
    """Test successful audio info retrieval."""
    mock_run.return_value = MagicMock(
        stdout=json.dumps(mock_audio_info),
        returncode=0,
    )

    processor = AudioProcessor(audio_config)
    info = processor.get_audio_info(sample_audio_path)

    assert info == mock_audio_info
    mock_run.assert_called_once()
    # Verify ffprobe command was called with the sample audio file
    assert str(sample_audio_path) in mock_run.call_args[0][0]


@patch("subprocess.run")
def test_get_audio_info_failure(mock_run, audio_config, sample_audio_path):
    """Test audio info retrieval failure."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")

    processor = AudioProcessor(audio_config)
    with pytest.raises(RuntimeError):
        processor.get_audio_info(sample_audio_path)


@patch("subprocess.run")
def test_get_audio_info_invalid_json(mock_run, audio_config, sample_audio_path):
    """Test handling of invalid JSON response from ffprobe."""
    mock_run.return_value = MagicMock(
        stdout="Invalid JSON",
        returncode=0,
    )

    processor = AudioProcessor(audio_config)
    with pytest.raises(RuntimeError):
        processor.get_audio_info(sample_audio_path)


def test_get_file_size_mb(audio_config, sample_audio_path):
    """Test file size calculation using actual sample file."""
    processor = AudioProcessor(audio_config)
    size_mb = processor.get_file_size_mb(sample_audio_path)

    # Sample file should exist and have a size
    assert size_mb > 0
    assert isinstance(size_mb, float)


def test_get_existing_splits(audio_config, test_data_dir, sample_audio_path):
    """Test detection of existing split files."""
    # Create mock split files based on the sample audio name
    base_name = sample_audio_path.stem
    splits = []
    for i in range(3):
        split_file = test_data_dir / f"{base_name}_part{i:03d}.mp3"
        split_file.touch()
        splits.append(split_file)

    processor = AudioProcessor(audio_config)
    found_splits = processor.get_existing_splits(sample_audio_path, test_data_dir)

    assert len(found_splits) == 3
    assert all(split in splits for split in found_splits)

    # Cleanup the split files
    for split in splits:
        split.unlink()
