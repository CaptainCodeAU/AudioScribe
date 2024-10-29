"""Pytest configuration and fixtures."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from openai import OpenAI

from audioscribe.config import AudioConfig


@pytest.fixture
def audio_config():
    """Create a test audio configuration."""
    return AudioConfig(
        FFMPEG_PATH="/usr/local/bin/ffmpeg",
        FFPROBE_PATH="/usr/local/bin/ffprobe",
        MAX_SPLIT_SIZE_MB=25,
        MAX_SPLIT_DURATION=600,
    )


@pytest.fixture
def mock_openai_client():
    """Create a mock OpenAI client with required attributes."""
    mock_client = MagicMock(spec=OpenAI)

    # Setup audio transcription mock chain
    mock_audio = MagicMock()
    mock_transcriptions = MagicMock()
    mock_client.audio = mock_audio
    mock_audio.transcriptions = mock_transcriptions

    # Setup chat completion mock chain
    mock_chat = MagicMock()
    mock_completions = MagicMock()
    mock_client.chat = mock_chat
    mock_chat.completions = mock_completions

    return mock_client


@pytest.fixture
def test_data_dir():
    """Return the actual test_data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture
def sample_audio_path(test_data_dir):
    """Return the path to the actual sample.mp3 file."""
    audio_path = test_data_dir / "sample.mp3"
    if not audio_path.exists():
        raise FileNotFoundError(f"Sample audio file not found at {audio_path}")
    return audio_path


@pytest.fixture
def mock_audio_info():
    """Create mock audio file information."""
    return {
        "streams": [{"bit_rate": "128000"}],
        "format": {"duration": "300.0"},
    }


@pytest.fixture
def mock_transcript_response():
    """Create a mock transcript response."""
    class MockResponse:
        def __init__(self):
            self.text = "This is a test transcript."
            self.model_dump = lambda: {
                "text": self.text,
                "language": "en",
                "duration": 300.0,
            }

    return MockResponse()


@pytest.fixture
def clean_env():
    """Fixture to provide a clean environment without API key."""
    original_env = dict(os.environ)
    os.environ.clear()
    # Restore any critical environment variables if needed, except OPENAI_API_KEY
    yield
    os.environ.clear()
    os.environ.update(original_env)
