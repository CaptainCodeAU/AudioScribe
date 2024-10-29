"""Tests for transcription functionality."""

import os
from pathlib import Path
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import OpenAI

from audioscribe.transcription import TranscriptionService, TranscriptCleaner


def test_transcription_service_initialization():
    """Test TranscriptionService initialization."""
    service = TranscriptionService()
    assert service.model == "whisper-1"


@patch('os.getenv')
@patch('dotenv.load_dotenv')
def test_transcription_service_missing_api_key(mock_load_dotenv, mock_getenv, clean_env):
    """Test TranscriptionService initialization with missing API key."""
    # Ensure load_dotenv doesn't actually load any environment variables
    mock_load_dotenv.return_value = False
    # Ensure getenv returns None for OPENAI_API_KEY
    mock_getenv.return_value = None

    with pytest.raises(ValueError, match="OPENAI_API_KEY not found in environment variables"):
        TranscriptionService()


def test_transcribe_file_success(mock_openai_client, sample_audio_path, mock_transcript_response):
    """Test successful file transcription."""
    # Setup mock client response
    mock_openai_client.audio.transcriptions.create.return_value = mock_transcript_response

    service = TranscriptionService()
    service.client = mock_openai_client

    text, metadata = service.transcribe_file(sample_audio_path)

    assert text == mock_transcript_response.text
    assert "file_info" in metadata
    assert metadata["file_info"]["original_filename"] == sample_audio_path.name


def test_transcribe_file_not_found(mock_openai_client):
    """Test transcription with non-existent file."""
    service = TranscriptionService()
    service.client = mock_openai_client

    with pytest.raises(FileNotFoundError):
        service.transcribe_file(Path("nonexistent.mp3"))


def test_transcribe_file_retry_success(mock_openai_client, sample_audio_path, mock_transcript_response):
    """Test successful transcription after retries.

    Note: The API Error log is expected here as we're testing the retry mechanism.
    The first attempt is designed to fail with an API Error, and the second attempt succeeds.
    """
    # First call fails, second succeeds
    mock_openai_client.audio.transcriptions.create.side_effect = [
        Exception("API Error"),
        mock_transcript_response,
    ]

    service = TranscriptionService()
    service.client = mock_openai_client

    text, metadata = service.transcribe_file(sample_audio_path, retries=2)

    assert text == mock_transcript_response.text
    assert mock_openai_client.audio.transcriptions.create.call_count == 2


def test_transcribe_file_all_retries_fail(mock_openai_client, sample_audio_path):
    """Test transcription failing after all retries.

    Note: The API Error logs are expected here as we're testing the failure handling.
    All attempts are designed to fail with API Errors to verify proper error handling.
    """
    mock_openai_client.audio.transcriptions.create.side_effect = Exception("API Error")

    service = TranscriptionService()
    service.client = mock_openai_client

    with pytest.raises(Exception, match="API Error"):
        service.transcribe_file(sample_audio_path, retries=2)

    assert mock_openai_client.audio.transcriptions.create.call_count == 2


def test_transcribe_file_with_timeout(mock_openai_client, sample_audio_path):
    """Test handling of timeout during transcription."""
    # Mock a timeout error
    mock_openai_client.audio.transcriptions.create.side_effect = httpx.TimeoutException("Request timed out")

    service = TranscriptionService()
    service.client = mock_openai_client

    with pytest.raises(Exception) as exc_info:
        service.transcribe_file(sample_audio_path, retries=1)

    assert "Request timed out" in str(exc_info.value)


def test_transcribe_file_with_different_models(mock_openai_client, sample_audio_path, mock_transcript_response):
    """Test transcription with different Whisper models."""
    models = ["whisper-1", "whisper-large"]

    for model in models:
        service = TranscriptionService(model=model)
        service.client = mock_openai_client
        mock_openai_client.audio.transcriptions.create.return_value = mock_transcript_response

        text, metadata = service.transcribe_file(sample_audio_path)

        # Verify the correct model was used in the API call
        call_args = mock_openai_client.audio.transcriptions.create.call_args
        assert call_args[1]["model"] == model


def test_transcribe_file_with_rate_limit(mock_openai_client, sample_audio_path, mock_transcript_response):
    """Test handling of API rate limits."""
    # Mock rate limit error followed by success
    mock_openai_client.audio.transcriptions.create.side_effect = [
        Exception("Rate limit exceeded"),
        mock_transcript_response
    ]

    service = TranscriptionService()
    service.client = mock_openai_client

    start_time = time.time()
    text, metadata = service.transcribe_file(sample_audio_path, retries=2)
    elapsed_time = time.time() - start_time

    # Verify that the rate limit retry included a delay
    assert elapsed_time > 1  # At least some delay should have occurred
    assert text == mock_transcript_response.text


def test_transcribe_file_with_large_file(mock_openai_client, tmp_path):
    """Test transcription of files near the size limit."""
    # Create a large temporary file (25MB)
    large_file = tmp_path / "large_audio.mp3"
    large_file.write_bytes(b"0" * (25 * 1024 * 1024))  # 25MB file

    service = TranscriptionService()
    service.client = mock_openai_client

    try:
        with pytest.raises(Exception, match="File size exceeds limit"):
            service.transcribe_file(large_file)
    finally:
        large_file.unlink()


def test_transcript_cleaner_initialization(mock_openai_client):
    """Test TranscriptCleaner initialization."""
    cleaner = TranscriptCleaner(mock_openai_client)
    assert cleaner.client == mock_openai_client


def test_clean_transcript_success(mock_openai_client, test_data_dir):
    """Test successful transcript cleaning."""
    # Create a mock transcript file
    transcript_path = test_data_dir / "test_transcript.txt"
    transcript_path.write_text("Original transcript text")

    try:
        # Mock GPT response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Cleaned transcript text"))
        ]
        mock_openai_client.chat.completions.create.return_value = mock_response

        cleaner = TranscriptCleaner(mock_openai_client)
        result_path = cleaner.clean_transcript(transcript_path)

        assert result_path.exists()
        assert result_path.read_text() == "Cleaned transcript text"
    finally:
        # Cleanup test files
        if transcript_path.exists():
            transcript_path.unlink()
        if result_path.exists():
            result_path.unlink()


def test_clean_transcript_file_not_found(mock_openai_client, test_data_dir):
    """Test cleaning non-existent transcript."""
    cleaner = TranscriptCleaner(mock_openai_client)

    with pytest.raises(FileNotFoundError):
        cleaner.clean_transcript(test_data_dir / "nonexistent.txt")


def test_clean_transcript_invalid_gpt_response(mock_openai_client, test_data_dir):
    """Test cleaning with invalid GPT response."""
    # Create a mock transcript file
    transcript_path = test_data_dir / "test_transcript.txt"
    transcript_path.write_text("Original transcript text")

    try:
        # Mock invalid GPT response
        mock_response = MagicMock()
        mock_response.choices = []
        mock_openai_client.chat.completions.create.return_value = mock_response

        cleaner = TranscriptCleaner(mock_openai_client)

        with pytest.raises(ValueError, match="Received invalid response from GPT"):
            cleaner.clean_transcript(transcript_path)
    finally:
        # Cleanup test file
        if transcript_path.exists():
            transcript_path.unlink()


def test_clean_transcript_with_long_content(mock_openai_client, test_data_dir):
    """Test cleaning of very long transcripts."""
    # Create a mock transcript file with long content
    transcript_path = test_data_dir / "test_transcript.txt"
    long_content = "Test content. " * 1000  # Create a long transcript
    transcript_path.write_text(long_content)

    try:
        # Mock GPT response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Cleaned long transcript"))
        ]
        mock_openai_client.chat.completions.create.return_value = mock_response

        cleaner = TranscriptCleaner(mock_openai_client)
        result_path = cleaner.clean_transcript(transcript_path)

        # Verify the API call
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args[1]["max_tokens"] == 4000  # Verify token limit is set

        assert result_path.exists()
        assert result_path.read_text() == "Cleaned long transcript"
    finally:
        # Cleanup test files
        if transcript_path.exists():
            transcript_path.unlink()
        if result_path.exists():
            result_path.unlink()


def test_clean_transcript_with_multiple_retries(mock_openai_client, test_data_dir):
    """Test transcript cleaning with multiple GPT API retries."""
    transcript_path = test_data_dir / "test_transcript.txt"
    transcript_path.write_text("Test content")

    try:
        # Mock multiple failures followed by success
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Cleaned content"))
        ]
        mock_openai_client.chat.completions.create.side_effect = [
            Exception("API Error"),
            Exception("Rate limit"),
            mock_response
        ]

        cleaner = TranscriptCleaner(mock_openai_client)
        result_path = cleaner.clean_transcript(transcript_path)

        assert result_path.exists()
        assert result_path.read_text() == "Cleaned content"
        assert mock_openai_client.chat.completions.create.call_count == 3
    finally:
        # Cleanup test files
        if transcript_path.exists():
            transcript_path.unlink()
        if result_path.exists():
            result_path.unlink()

