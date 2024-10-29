"""Transcript management module for AudioScribe."""

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


class TranscriptManager:
    """Manages transcript files and their processing."""

    def __init__(self, transcript_dir: Path):
        self.transcript_dir = transcript_dir
        if not self.transcript_dir.exists():
            logger.debug(f"Creating transcript directory: {self.transcript_dir}")
            self.transcript_dir.mkdir(parents=True, exist_ok=True)

    def check_existing_transcripts(self, file_path: Path) -> bool:
        """Check if transcription files already exist for the given audio file."""
        # Get filename without the actual extension
        base_name = self._get_base_filename(file_path)
        txt_path = self.transcript_dir / f"{base_name}.txt"
        json_path = self.transcript_dir / f"{base_name}.json"

        if txt_path.exists() and json_path.exists():
            # Check if files have content
            if txt_path.stat().st_size > 0 and json_path.stat().st_size > 0:
                logger.info(f"Found existing transcription files for {file_path.name}")
                return True
        return False

    def _get_base_filename(self, file_path: Path) -> str:
        """Extract base filename without the actual file extension."""
        # Get the actual file extension (e.g., .wav, .mp3)
        actual_extension = file_path.suffix
        # Remove only the actual extension from the filename
        return file_path.name[:-len(actual_extension)] if actual_extension else file_path.name

    def save_transcript(self, text: str, metadata: dict, original_file: Path) -> tuple[Path, Path]:
        """Save transcription results to both text and JSON files."""
        # Get base name without the actual extension
        base_name = self._get_base_filename(original_file)

        # Create paths for transcript files
        txt_path = self.transcript_dir / f"{base_name}.txt"
        json_path = self.transcript_dir / f"{base_name}.json"

        logger.debug(f"Saving transcript to: {txt_path}")

        # Save text version
        try:
            logger.debug(f"Writing text file: {txt_path}")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Failed to save text file {txt_path}: {e}")
            raise

        # Save JSON version with metadata
        try:
            logger.debug(f"Writing JSON file: {json_path}")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Failed to save JSON file {json_path}: {e}")
            raise

        # Verify files exist and have content
        if not txt_path.exists() or txt_path.stat().st_size == 0:
            raise RuntimeError(f"Failed to save or verify transcript at {txt_path}")

        if not json_path.exists() or json_path.stat().st_size == 0:
            raise RuntimeError(f"Failed to save or verify metadata at {json_path}")

        return txt_path, json_path

    def merge_transcripts(self) -> None:
        """Merge transcript files for all audio series."""
        logger.info("Starting transcript merge process")

        # Function to extract part number from filename
        def get_part_number(filename: str) -> int:
            match = re.search(r"part(\d+)", filename)
            return int(match.group(1)) if match else -1

        # Function to get base series name from filename
        def get_series_name(filename: str) -> str:
            # Remove _partNNN.txt or _partNNN.clean.txt
            return re.sub(r"_part\d+\.(clean\.)?txt$", "", filename)

        try:
            # Get all transcript files that have parts
            all_files = list(self.transcript_dir.glob("*part*.txt"))

            # Extract unique series names
            series_names = set()
            for file in all_files:
                series_name = get_series_name(file.name)
                if series_name:
                    series_names.add(series_name)

            if not series_names:
                logger.info("No series files found to merge")
                return

            logger.info(f"Found series to merge: {series_names}")

            # Process each series
            for series in sorted(series_names):
                # Merge regular transcripts
                pattern = f"{series}_part*.txt"
                output_file = f"{series}.txt"

                # Get all matching files for this series
                files = sorted(
                    [
                        f
                        for f in self.transcript_dir.glob(pattern)
                        if not f.name.endswith(".clean.txt")
                    ],
                    key=lambda x: get_part_number(x.name),
                )

                if files:
                    merged_content = []
                    for file in files:
                        try:
                            with open(file, encoding="utf-8") as f:
                                content = f.read().strip()
                                if content:  # Only add non-empty content
                                    merged_content.append(content)
                        except Exception as e:
                            logger.error(f"Error reading file {file}: {e}")
                            raise

                    if merged_content:
                        output_path = self.transcript_dir / output_file
                        try:
                            with open(output_path, "w", encoding="utf-8") as f:
                                f.write("\n\n".join(merged_content))
                            logger.info(f"Successfully created merged file: {output_path}")
                        except Exception as e:
                            logger.error(f"Error writing merged file {output_path}: {e}")
                            raise

                # Merge clean transcripts
                pattern = f"{series}_part*.clean.txt"
                output_file = f"{series}.clean.txt"

                # Get all matching files for this series
                files = sorted(
                    [f for f in self.transcript_dir.glob(pattern)],
                    key=lambda x: get_part_number(x.name),
                )

                if files:
                    merged_content = []
                    for file in files:
                        try:
                            with open(file, encoding="utf-8") as f:
                                content = f.read().strip()
                                if content:  # Only add non-empty content
                                    merged_content.append(content)
                        except Exception as e:
                            logger.error(f"Error reading file {file}: {e}")
                            raise

                    if merged_content:
                        output_path = self.transcript_dir / output_file
                        try:
                            with open(output_path, "w", encoding="utf-8") as f:
                                f.write("\n\n".join(merged_content))
                            logger.info(f"Successfully created merged file: {output_path}")
                        except Exception as e:
                            logger.error(f"Error writing merged file {output_path}: {e}")
                            raise

        except Exception as e:
            logger.error(f"Error during transcript merge: {e}")
            raise
