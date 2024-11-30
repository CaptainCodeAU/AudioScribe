"""
Audio processing module for AudioScribe.

This module provides functionality for processing audio files, including
splitting large audio files into smaller segments for easier processing.
"""

import json
import logging
import os
import subprocess
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, ClassVar, NoReturn

from .config import AudioConfig

logger = logging.getLogger(__name__)

# Error messages
TIMEOUT_ERROR = "Command execution timed out after 5 minutes"
INVALID_COMMAND_ERROR = "Invalid command arguments"
COMMAND_NOT_FOUND = "Command not found: {}"
COMMAND_NOT_ALLOWED = "Command not allowed: {}"
AUDIO_FILE_NOT_FOUND = "Audio file not found: {}"
INVALID_JSON_ERROR = "Failed to parse ffprobe output: Invalid JSON"
COMMAND_ERROR = "Failed to get audio info: {}"
INVALID_BITRATE_ERROR = "Invalid bit rate: not a valid number"
INVALID_DURATION_ERROR = "Invalid duration: not a valid number"
SPLIT_ERROR = "Failed to split audio file: {}"
NO_SPLITS_ERROR = "No split files were created for {}"
CONVERSION_ERROR = "Failed to convert audio file: {}"


@dataclass(frozen=True)
class SubprocessConfig:
    """Configuration for subprocess execution."""

    cmd: Sequence[str | Path]
    check: bool = True
    capture_output: bool = True


class AudioProcessor:
    """Handles all audio-related operations."""

    # Whitelist of allowed commands for security
    ALLOWED_COMMANDS: ClassVar[set[str]] = {"ffmpeg", "ffprobe"}

    def __init__(self, config: AudioConfig) -> None:
        """
        Initialize AudioProcessor with configuration.

        Args:
            config: Configuration object containing audio-related settings.

        """
        self.config = config
        self._lock = Lock()  # Add lock for thread safety
        os.environ["PATH"] = f"{Path(config.FFMPEG_PATH).parent}:{os.environ['PATH']}"

    def _raise_invalid_command(self) -> NoReturn:
        """Raise error for invalid command arguments."""
        logger.error(INVALID_COMMAND_ERROR)
        raise ValueError(INVALID_COMMAND_ERROR)

    def _raise_invalid_value(self, msg: str) -> NoReturn:
        """Raise error for invalid value."""
        logger.error(msg)
        raise ValueError(msg)

    def _validate_command_path(self, cmd_path: Path) -> None:
        """
        Validate command path for security.

        Args:
            cmd_path: Path to the command executable.

        Raises:
            ValueError: If command path is invalid or not allowed.

        """
        if not cmd_path.is_file():
            msg = COMMAND_NOT_FOUND.format(cmd_path)
            logger.error(msg)
            raise ValueError(msg)

        if cmd_path.name not in self.ALLOWED_COMMANDS:
            msg = COMMAND_NOT_ALLOWED.format(cmd_path.name)
            logger.error(msg)
            raise ValueError(msg)

    def _secure_run(self, config: SubprocessConfig) -> subprocess.CompletedProcess:
        """
        Securely run a subprocess command.

        Args:
            config: Subprocess configuration.

        Returns:
            CompletedProcess: Result of the command execution.

        Raises:
            ValueError: If command is not in whitelist.
            subprocess.CalledProcessError: If command fails.

        """
        if not config.cmd:
            self._raise_invalid_command()

        # Validate command path
        cmd_path = Path(str(config.cmd[0]))
        self._validate_command_path(cmd_path)

        # Convert all arguments to strings but don't quote them
        # subprocess.run will handle escaping properly
        cmd = [str(arg) for arg in config.cmd]

        # Use a restricted environment for security
        env = {
            "PATH": os.environ["PATH"],
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }

        logger.debug("Executing command: %s", " ".join(cmd))

        try:
            process = subprocess.run(
                cmd,
                check=config.check,
                capture_output=config.capture_output,
                encoding="utf-8",
                shell=False,  # Important: shell=False for security
                text=True,
                env=env,
                timeout=300  # 5 minute timeout
            )
            logger.debug("Command completed successfully")
            return process
        except subprocess.TimeoutExpired as err:
            logger.exception(TIMEOUT_ERROR)
            raise RuntimeError(TIMEOUT_ERROR) from err

    def _raise_file_not_found(self, file_path: Path) -> NoReturn:
        """Raise error for file not found."""
        msg = AUDIO_FILE_NOT_FOUND.format(file_path)
        logger.exception(msg)
        raise RuntimeError(msg)

    def _raise_invalid_json(self, err: json.JSONDecodeError) -> NoReturn:
        """Raise error for invalid JSON."""
        logger.exception(INVALID_JSON_ERROR)
        raise RuntimeError(INVALID_JSON_ERROR) from err

    def _raise_command_error(self, e: subprocess.CalledProcessError) -> NoReturn:
        """Raise error for command execution failure."""
        msg = COMMAND_ERROR.format(e)
        logger.exception(msg)
        raise RuntimeError(msg) from e

    def convert_m4a_to_mp3(self, file_path: Path) -> Path:
        """
        Convert M4A file to MP3 format using ffmpeg.

        Args:
            file_path: Path to the M4A file.

        Returns:
            Path: Path to the converted MP3 file.

        Raises:
            RuntimeError: If conversion fails.
        """
        if not file_path.is_file():
            self._raise_file_not_found(file_path)

        if file_path.suffix.lower() != '.m4a':
            return file_path

        output_path = file_path.with_suffix('.mp3')

        # Skip if MP3 already exists
        if output_path.exists():
            logger.info("MP3 file already exists for %s, skipping conversion", file_path.name)
            return output_path

        logger.info("Converting %s to MP3 format", file_path.name)

        cmd = [
            self.config.FFMPEG_PATH,
            "-i",
            str(file_path),
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "2",  # VBR quality setting (2 is high quality)
            str(output_path)
        ]

        try:
            self._secure_run(SubprocessConfig(cmd=cmd))
            logger.info("Successfully converted %s to MP3", file_path.name)
            return output_path
        except subprocess.CalledProcessError as e:
            msg = CONVERSION_ERROR.format(e)
            logger.exception(msg)
            if output_path.exists():
                output_path.unlink()
            raise RuntimeError(msg) from e

    def get_audio_info(self, file_path: Path) -> dict[str, Any]:
        """
        Get audio file information using ffprobe.

        Args:
            file_path: Path to the audio file.

        Returns:
            dict: Audio file information including format and streams.

        Raises:
            RuntimeError: If ffprobe fails or returns invalid output.

        """
        if not file_path.is_file():
            self._raise_file_not_found(file_path)

        cmd = [
            self.config.FFPROBE_PATH,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=bit_rate",
            "-of",
            "json",
            str(file_path),  # Path will be properly escaped by subprocess.run
        ]

        try:
            result = self._secure_run(SubprocessConfig(cmd=cmd))
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError as err:
                self._raise_invalid_json(err)
        except subprocess.CalledProcessError as e:
            self._raise_command_error(e)

    def get_file_size_mb(self, file_path: Path) -> float:
        """
        Get file size in MB.

        Args:
            file_path: Path to the file.

        Returns:
            float: File size in megabytes.

        """
        size_bytes = file_path.stat().st_size
        return size_bytes / (1024 * 1024)

    def get_existing_splits(self, file_path: Path, output_dir: Path) -> list[Path]:
        """
        Check for existing split files.

        Args:
            file_path: Original audio file path.
            output_dir: Directory containing split files.

        Returns:
            list[Path]: List of paths to existing split files.

        """
        # Remove lock since it's causing issues and isn't necessary for this operation
        return sorted(output_dir.glob(f"{file_path.stem}_part*.mp3"))

    def _raise_invalid_bitrate(self, err: Exception) -> NoReturn:
        """Raise error for invalid bitrate."""
        logger.exception(INVALID_BITRATE_ERROR)
        raise RuntimeError(INVALID_BITRATE_ERROR) from err

    def _raise_invalid_duration(self, err: Exception) -> NoReturn:
        """Raise error for invalid duration."""
        logger.exception(INVALID_DURATION_ERROR)
        raise RuntimeError(INVALID_DURATION_ERROR) from err

    def _validate_audio_metadata(self, info: dict[str, Any]) -> tuple[int, float]:
        """
        Validate audio metadata from ffprobe output.

        Args:
            info: Audio metadata dictionary.

        Returns:
            tuple: Validated bitrate and duration.

        Raises:
            RuntimeError: If metadata is invalid.

        """
        try:
            bitrate = int(info["streams"][0]["bit_rate"])
            if bitrate <= 0:
                self._raise_invalid_value("Bitrate must be positive")
        except (ValueError, KeyError) as err:
            self._raise_invalid_bitrate(err)

        try:
            duration = float(info["format"]["duration"])
            if duration <= 0:
                self._raise_invalid_value("Duration must be positive")
        except (ValueError, KeyError) as err:
            self._raise_invalid_duration(err)

        return bitrate, duration

    def _raise_split_error(self, e: subprocess.CalledProcessError) -> NoReturn:
        """Raise error for split operation failure."""
        msg = SPLIT_ERROR.format(e)
        logger.exception(msg)
        raise RuntimeError(msg) from e

    def _perform_split(
        self,
        file_path: Path,
        output_template: Path,
        segment_duration: float
    ) -> None:
        """
        Perform the actual audio splitting operation.

        Args:
            file_path: Input audio file path.
            output_template: Template for output file names.
            segment_duration: Duration of each segment.

        Raises:
            RuntimeError: If splitting operation fails.

        """
        logger.info("Starting to split file: %s", file_path)
        logger.info("Output template: %s", output_template)
        logger.info("Segment duration: %s seconds", segment_duration)

        cmd = [
            self.config.FFMPEG_PATH,
            "-i",
            str(file_path),
            "-f",
            "segment",
            "-segment_time",
            str(segment_duration),
            "-c",
            "copy",
            str(output_template),
        ]

        try:
            self._secure_run(SubprocessConfig(cmd=cmd))
            logger.info("Split operation completed successfully")
        except subprocess.CalledProcessError as e:
            self._raise_split_error(e)
        except Exception:
            logger.exception("Unexpected error during split")
            raise

    def _raise_no_splits_created(self, file_path: Path) -> NoReturn:
        """Raise error when no split files were created."""
        msg = NO_SPLITS_ERROR.format(file_path)
        logger.exception(msg)
        raise RuntimeError(msg)

    def split_audio(self, file_path: Path, output_dir: Path) -> list[Path]:
        """
        Split audio file into smaller segments.

        Args:
            file_path: Path to the audio file to split.
            output_dir: Directory to store split files.

        Returns:
            list[Path]: List of paths to split audio files.

        Raises:
            RuntimeError: If splitting fails or audio file is invalid.

        """
        try:
            # Convert M4A to MP3 if necessary
            if file_path.suffix.lower() == '.m4a':
                file_path = self.convert_m4a_to_mp3(file_path)

            # Check for existing splits first
            existing_splits = self.get_existing_splits(file_path, output_dir)
            if existing_splits:
                logger.info(
                    "Found existing split files for %s, skipping split operation",
                    file_path.name
                )
                return existing_splits

            # Validate input path
            if not file_path.is_file():
                self._raise_file_not_found(file_path)

            # Get and validate audio metadata
            info = self.get_audio_info(file_path)
            bitrate, _ = self._validate_audio_metadata(info)

            # Calculate optimal segment duration
            size_based_duration = (self.config.MAX_SPLIT_SIZE_MB * 8 * 1024 * 1024) / bitrate
            segment_duration = min(size_based_duration, self.config.MAX_SPLIT_DURATION)

            # Prepare output template
            output_template = output_dir / f"{file_path.stem}_part%03d.mp3"
            output_dir.mkdir(parents=True, exist_ok=True)

            logger.info("Starting audio split process")
            logger.info("Input file: %s", file_path)
            logger.info("File size: %.2f MB", self.get_file_size_mb(file_path))
            logger.info("Calculated segment duration: %.2f seconds", segment_duration)

            # Perform the split operation
            self._perform_split(file_path, output_template, segment_duration)

            # Get the list of split files
            split_files = sorted(output_dir.glob(f"{file_path.stem}_part*.mp3"))
            logger.info("Created %d split files", len(split_files))

            if not split_files:
                self._raise_no_splits_created(file_path)
            else:
                return split_files

        except Exception:
            logger.exception("Error during audio split process")
            # Clean up any partial files on error
            for split in output_dir.glob(f"{file_path.stem}_part*.mp3"):
                with suppress(Exception):
                    split.unlink()
                    logger.debug("Cleaned up partial file: %s", split)
            raise
