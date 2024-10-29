"""Configuration settings for AudioScribe."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup debug logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """Configuration settings for audio processing."""

    MAX_SPLIT_SIZE_MB: int = 5
    MAX_SPLIT_DURATION: int = 600  # 10 minutes in seconds
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25 MB (OpenAI limit)
    SUPPORTED_FORMATS: tuple = (".mp3", ".wav")
    FFMPEG_PATH: str = ""  # Will be set in post_init
    FFPROBE_PATH: str = ""  # Will be set in post_init

    def __post_init__(self):
        """Validate required environment variables."""
        self.FFMPEG_PATH = os.getenv("FFMPEG_PATH", "")
        self.FFPROBE_PATH = os.getenv("FFPROBE_PATH", "")

        if not self.FFMPEG_PATH:
            raise ValueError("FFMPEG_PATH not found in environment variables")
        if not self.FFPROBE_PATH:
            raise ValueError("FFPROBE_PATH not found in environment variables")


class ProjectPaths:
    """Project directory structure."""

    def __init__(self) -> None:
        """Initialize project paths and create necessary directories."""
        # Get the absolute path of the current working directory
        self.BASE_DIR = Path.cwd()
        logger.debug("Base directory: %s", self.BASE_DIR)

        # Define paths
        self.ORIGINAL = self.BASE_DIR / "data/original"
        self.SPLITS = self.BASE_DIR / "data/splits"
        self.TRANSCRIPTS = self.BASE_DIR / "data/transcripts"

        # Create directories
        self._create_directories()

    def _create_directories(self) -> None:
        """Create all required directories."""
        for path_name, path in {
            "ORIGINAL": self.ORIGINAL,
            "SPLITS": self.SPLITS,
            "TRANSCRIPTS": self.TRANSCRIPTS,
        }.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
                logger.debug("Created/verified directory %s: %s", path_name, path)
            except Exception as e:
                logger.error("Error creating directory %s: %s", path, e)
                raise
