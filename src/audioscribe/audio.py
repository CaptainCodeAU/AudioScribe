"""Audio processing module for AudioScribe."""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from threading import Lock

from .config import AudioConfig

logger = logging.getLogger(__name__)


class AudioProcessor:
    """Handles all audio-related operations."""

    def __init__(self, config: AudioConfig):
        self.config = config
        self._lock = Lock()  # Add lock for thread safety
        os.environ["PATH"] = f"{os.path.dirname(config.FFMPEG_PATH)}:{os.environ['PATH']}"

    def get_audio_info(self, file_path: Path) -> dict:
        """Get audio file information using ffprobe."""
        cmd = [
            self.config.FFPROBE_PATH,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=bit_rate",
            "-of",
            "json",
            str(file_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                raise RuntimeError("Failed to parse ffprobe output: Invalid JSON")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get audio info: {e}")

    def get_file_size_mb(self, file_path: Path) -> float:
        """Get file size in MB."""
        size_bytes = file_path.stat().st_size
        return size_bytes / (1024 * 1024)

    def get_existing_splits(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Check for existing split files."""
        with self._lock:  # Lock during file system operations
            existing_splits = sorted(output_dir.glob(f"{file_path.stem}_part*.mp3"))
            return existing_splits

    def split_audio(self, file_path: Path, output_dir: Path) -> list[Path]:
        """Split audio file into smaller segments."""
        with self._lock:  # Ensure thread safety for concurrent operations
            try:
                # Check for existing splits first
                existing_splits = self.get_existing_splits(file_path, output_dir)
                if existing_splits:
                    logger.info(
                        f"Found existing split files for {file_path.name}, skipping split operation"
                    )
                    return existing_splits

                info = self.get_audio_info(file_path)

                # Validate bitrate
                try:
                    bitrate = int(info["streams"][0]["bit_rate"])
                    if bitrate <= 0:
                        raise RuntimeError("Invalid bit rate: must be positive")
                except (ValueError, KeyError):
                    raise RuntimeError("Invalid bit rate: not a valid number")

                # Validate duration
                try:
                    total_duration = float(info["format"]["duration"])
                    if total_duration <= 0:
                        raise RuntimeError("Invalid duration: must be positive")
                except (ValueError, KeyError):
                    raise RuntimeError("Invalid duration: not a valid number")

                # Calculate optimal segment duration
                size_based_duration = (self.config.MAX_SPLIT_SIZE_MB * 8 * 1024 * 1024) / bitrate
                segment_duration = min(size_based_duration, self.config.MAX_SPLIT_DURATION)

                # Prepare output template - removed timestamp
                output_template = output_dir / f"{file_path.stem}_part%03d.mp3"

                logger.debug(f"Splitting audio file: {file_path}")
                logger.debug(f"Output template: {output_template}")

                # Split audio
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

                subprocess.run(cmd, check=True)

                # Wait for file system
                time.sleep(2)

                # Get the list of split files
                split_files = sorted(output_dir.glob(f"{file_path.stem}_part*.mp3"))
                logger.debug(f"Created {len(split_files)} split files")

                if not split_files:
                    raise RuntimeError(f"No split files were created for {file_path}")

                return split_files

            except Exception as e:
                # Clean up any partial files on error
                for split in output_dir.glob(f"{file_path.stem}_part*.mp3"):
                    try:
                        split.unlink()
                    except Exception:
                        pass
                raise
