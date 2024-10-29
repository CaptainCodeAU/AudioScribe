"""Transcription service module for AudioScribe."""

import logging
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

# OpenAI's Whisper API has a 25MB file size limit
MAX_FILE_SIZE_MB = 25


class TranscriptionService:
    """Handles all transcription-related operations."""

    def __init__(self, model: str = "whisper-1"):
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        self.client = OpenAI(
            api_key=api_key,
            max_retries=5,
            timeout=httpx.Timeout(600.0, read=300.0, write=10.0, connect=5.0),
        )
        self.model = model

    def transcribe_file(self, file_path: Path, retries: int = 3) -> tuple[str, dict]:
        """Transcribe a single audio file with retries."""
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        # Check file size before attempting transcription
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb >= MAX_FILE_SIZE_MB:  # Changed > to >= for exact limit
            raise Exception(f"File size exceeds limit of {MAX_FILE_SIZE_MB}MB")

        logger.debug(f"Starting transcription of {file_path}")

        for attempt in range(retries):
            try:
                with file_path.open("rb") as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model=self.model, file=audio_file, response_format="verbose_json"
                    )

                    # Convert response to dict for metadata
                    response_dict = response.model_dump()

                    # Add additional metadata
                    response_dict["file_info"] = {
                        "original_filename": file_path.name,
                        "file_size": file_path.stat().st_size,
                        "transcription_timestamp": datetime.now().isoformat(),
                    }

                    logger.debug(f"Successfully transcribed {file_path}")
                    return response.text, response_dict

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {file_path}: {e}")
                if attempt == retries - 1:
                    raise
                wait_time = 30 * (2**attempt)
                time.sleep(wait_time)

        raise RuntimeError(f"Failed to transcribe {file_path} after {retries} attempts")


class TranscriptCleaner:
    """Handles cleaning and refinement of transcripts."""

    def __init__(self, client: OpenAI):
        self.client = client
        self.logger = logging.getLogger(__name__)

    def _get_base_filename(self, file_path: Path) -> str:
        """Extract base filename without the actual file extension."""
        # Get the actual file extension (e.g., .txt)
        actual_extension = "".join(file_path.suffixes[-1:])  # Get only the last suffix
        # Remove only the actual extension from the filename
        return file_path.name[:-len(actual_extension)] if actual_extension else file_path.name

    def clean_transcript(self, transcript_path: Path, retries: int = 3) -> Path:
        """Clean up a transcript file using GPT model."""
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

        # Generate clean file path using base filename
        base_name = self._get_base_filename(transcript_path)
        clean_path = transcript_path.parent / f"{base_name}.clean.txt"

        # Check if clean version already exists
        if clean_path.exists():
            self.logger.info(f"Clean version already exists: {clean_path}")
            return clean_path

        # Read original transcript
        with transcript_path.open("r", encoding="utf-8") as f:
            content = f.read()

        # Prepare prompt for cleaning
        prompt = (
            "Clean up this transcription by removing redundant phrases and making "
            "sentences more coherent. Preserve all information and do not summarize. "
            "The goal is to improve readability while maintaining complete accuracy:\n\n"
            f"{content}"
        )

        for attempt in range(retries):
            try:
                # Get cleaned version from GPT
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional transcript editor. Clean up the text while preserving all information.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=4000,
                )

                # Safely extract cleaned text from response
                if (
                    not response.choices
                    or not response.choices[0].message
                    or not response.choices[0].message.content
                ):
                    raise ValueError("Received invalid response from GPT")

                cleaned_text = response.choices[0].message.content.strip()

                # Save cleaned version
                with clean_path.open("w", encoding="utf-8") as f:
                    f.write(cleaned_text)

                self.logger.info(f"Created cleaned transcript: {clean_path}")
                return clean_path

            except Exception as e:
                self.logger.error(f"Attempt {attempt + 1} failed for {transcript_path}: {e}")
                if attempt == retries - 1:
                    raise
                wait_time = 30 * (2**attempt)
                time.sleep(wait_time)

        raise RuntimeError(f"Failed to clean transcript {transcript_path} after {retries} attempts")
