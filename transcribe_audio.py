import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI, AuthenticationError, RateLimitError, APIError
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import subprocess
import time

# Initialize Rich console for better output formatting
console = Console()

# Setup debug logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class AudioConfig:
    """Configuration settings for audio processing"""
    MAX_SPLIT_SIZE_MB: int = 5
    MAX_SPLIT_DURATION: int = 600  # 10 minutes in seconds
    MAX_FILE_SIZE: int = 25 * 1024 * 1024  # 25 MB (OpenAI limit)
    SUPPORTED_FORMATS: tuple = ('.mp3', '.wav', '.m4a')
    FFMPEG_PATH: str = "/Users/admin/Documents/apps/ffmpeg"
    FFPROBE_PATH: str = "/Users/admin/Documents/apps/ffprobe"

class ProjectPaths:
    """Project directory structure"""
    def __init__(self):
        # Get the absolute path of the current working directory
        self.BASE_DIR = Path.cwd()
        logger.debug(f"Base directory: {self.BASE_DIR}")

        # Define paths
        self.ORIGINAL = self.BASE_DIR / "data/original"
        self.SPLITS = self.BASE_DIR / "data/splits"
        self.TRANSCRIPTS = self.BASE_DIR / "data/transcripts"

        # Create directories
        self._create_directories()

    def _create_directories(self):
        """Create all required directories"""
        for path_name, path in {
            "ORIGINAL": self.ORIGINAL,
            "SPLITS": self.SPLITS,
            "TRANSCRIPTS": self.TRANSCRIPTS
        }.items():
            try:
                path.mkdir(parents=True, exist_ok=True)
                logger.debug(f"Created/verified directory {path_name}: {path}")
            except Exception as e:
                logger.error(f"Error creating directory {path}: {e}")
                raise

class AudioProcessor:
    """Handles all audio-related operations"""

    def __init__(self, config: AudioConfig):
        self.config = config
        os.environ["PATH"] = f"{os.path.dirname(config.FFMPEG_PATH)}:{os.environ['PATH']}"

    def get_audio_info(self, file_path: Path) -> dict:
        """Get audio file information using ffprobe"""
        cmd = [
            self.config.FFPROBE_PATH,
            "-v", "error",
            "-show_entries", "format=duration:stream=bit_rate",
            "-of", "json",
            str(file_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return json.loads(result.stdout)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to get audio info: {e}")

    def get_file_size_mb(self, file_path: Path) -> float:
        """Get file size in MB"""
        size_bytes = file_path.stat().st_size
        return size_bytes / (1024 * 1024)

    def get_existing_splits(self, file_path: Path, output_dir: Path) -> List[Path]:
        """Check for existing split files"""
        existing_splits = sorted(output_dir.glob(f"{file_path.stem}_part*.mp3"))
        return existing_splits

    def split_audio(self, file_path: Path, output_dir: Path) -> List[Path]:
        """Split audio file into smaller segments"""
        # Check for existing splits first
        existing_splits = self.get_existing_splits(file_path, output_dir)
        if existing_splits:
            logger.info(f"Found existing split files for {file_path.name}, skipping split operation")
            return existing_splits

        info = self.get_audio_info(file_path)

        # Calculate optimal segment duration
        bitrate = int(info["streams"][0]["bit_rate"])
        total_duration = float(info["format"]["duration"])
        size_based_duration = (self.config.MAX_SPLIT_SIZE_MB * 8 * 1024 * 1024) / bitrate
        segment_duration = min(size_based_duration, self.config.MAX_SPLIT_DURATION)

        # Prepare output template - removed timestamp
        output_template = output_dir / f"{file_path.stem}_part%03d.mp3"

        logger.debug(f"Splitting audio file: {file_path}")
        logger.debug(f"Output template: {output_template}")

        # Split audio
        cmd = [
            self.config.FFMPEG_PATH,
            "-i", str(file_path),
            "-f", "segment",
            "-segment_time", str(segment_duration),
            "-c", "copy",
            str(output_template)
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

class TranscriptionService:
    """Handles all transcription-related operations"""

    def __init__(self, model: str = "whisper-1"):
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        self.client = OpenAI(
            api_key=api_key,
            max_retries=5,
            timeout=httpx.Timeout(600.0, read=300.0, write=10.0, connect=5.0)
        )
        self.model = model

    def transcribe_file(self, file_path: Path, retries: int = 3) -> Tuple[str, dict]:
        """Transcribe a single audio file with retries"""
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        logger.debug(f"Starting transcription of {file_path}")

        for attempt in range(retries):
            try:
                with file_path.open("rb") as audio_file:
                    response = self.client.audio.transcriptions.create(
                        model=self.model,
                        file=audio_file,
                        response_format="verbose_json"
                    )

                    # Convert response to dict for metadata
                    response_dict = response.model_dump()

                    # Add additional metadata
                    response_dict["file_info"] = {
                        "original_filename": file_path.name,
                        "file_size": file_path.stat().st_size,
                        "transcription_timestamp": datetime.now().isoformat()
                    }

                    logger.debug(f"Successfully transcribed {file_path}")
                    return response.text, response_dict

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {file_path}: {e}")
                if attempt == retries - 1:
                    raise
                wait_time = 30 * (2 ** attempt)
                time.sleep(wait_time)

        raise RuntimeError(f"Failed to transcribe {file_path} after {retries} attempts")

class TranscriptCleaner:
    """Handles cleaning and refinement of transcripts"""

    def __init__(self, client: OpenAI):
        self.client = client
        self.logger = logging.getLogger(__name__)

    def clean_transcript(self, transcript_path: Path) -> Path:
        """Clean up a transcript file using GPT model"""
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

        # Generate clean file path
        clean_path = transcript_path.parent / f"{transcript_path.stem}.clean.txt"

        # Check if clean version already exists
        if clean_path.exists():
            self.logger.info(f"Clean version already exists: {clean_path}")
            return clean_path

        try:
            # Read original transcript
            with transcript_path.open('r', encoding='utf-8') as f:
                content = f.read()

            # Prepare prompt for cleaning
            prompt = (
                "Clean up this transcription by removing redundant phrases and making "
                "sentences more coherent. Preserve all information and do not summarize. "
                "The goal is to improve readability while maintaining complete accuracy:\n\n"
                f"{content}"
            )

            # Get cleaned version from GPT
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional transcript editor. Clean up the text while preserving all information."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )

            # Safely extract cleaned text from response
            if not response.choices or not response.choices[0].message or not response.choices[0].message.content:
                raise ValueError("Received invalid response from GPT")

            cleaned_text = response.choices[0].message.content.strip()

            # Save cleaned version
            with clean_path.open('w', encoding='utf-8') as f:
                f.write(cleaned_text)

            self.logger.info(f"Created cleaned transcript: {clean_path}")
            return clean_path

        except Exception as e:
            self.logger.error(f"Failed to clean transcript {transcript_path}: {e}")
            raise

class TranscriptManager:
    """Manages transcript files and their processing"""

    def __init__(self, transcript_dir: Path):
        self.transcript_dir = transcript_dir
        if not self.transcript_dir.exists():
            logger.debug(f"Creating transcript directory: {self.transcript_dir}")
            self.transcript_dir.mkdir(parents=True, exist_ok=True)

    def check_existing_transcripts(self, file_path: Path) -> bool:
        """Check if transcription files already exist for the given audio file"""
        base_name = self.transcript_dir / file_path.stem
        txt_path = base_name.with_suffix('.txt')
        json_path = base_name.with_suffix('.json')

        if txt_path.exists() and json_path.exists():
            # Check if files have content
            if txt_path.stat().st_size > 0 and json_path.stat().st_size > 0:
                logger.info(f"Found existing transcription files for {file_path.name}")
                return True
        return False

    def save_transcript(self, text: str, metadata: dict, original_file: Path) -> Tuple[Path, Path]:
        """Save transcription results to both text and JSON files"""
        # Removed timestamp from base_name
        base_name = self.transcript_dir / f"{original_file.stem}"

        logger.debug(f"Saving transcript to: {base_name}")

        # Save text version
        txt_path = base_name.with_suffix('.txt')
        try:
            logger.debug(f"Writing text file: {txt_path}")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error(f"Failed to save text file {txt_path}: {e}")
            raise

        # Save JSON version with metadata
        json_path = base_name.with_suffix('.json')
        try:
            logger.debug(f"Writing JSON file: {json_path}")
            with open(json_path, 'w', encoding='utf-8') as f:
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

class AudioTranscriptionPipeline:
    """Main pipeline orchestrating the entire transcription process"""

    def __init__(self):
        self.config = AudioConfig()
        self.paths = ProjectPaths()
        self.audio_processor = AudioProcessor(self.config)
        self.transcription_service = TranscriptionService()
        self.transcript_manager = TranscriptManager(self.paths.TRANSCRIPTS)
        self.transcript_cleaner = TranscriptCleaner(self.transcription_service.client)
        self.logger = logging.getLogger(__name__)

    def process_file(self, file_path: Path) -> None:
        """Process a single audio file"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if file_path.suffix.lower() not in self.config.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

        # Check if file needs splitting
        if file_path.stat().st_size > self.config.MAX_FILE_SIZE:
            self.logger.info(f"Large file detected: {file_path}")
            split_files = self.audio_processor.split_audio(file_path, self.paths.SPLITS)

            # Process each split individually
            for split_file in split_files:
                try:
                    # Check if transcription already exists for this split
                    if self.transcript_manager.check_existing_transcripts(split_file):
                        console.print(f"[yellow]Skipping transcription for {split_file.name} - already exists[/yellow]")
                        continue
                    self._process_single_file(split_file)
                except Exception as e:
                    logger.error(f"Failed to process split file {split_file}: {e}")
                    console.print(f"[red]Failed to process split file {split_file}: {e}[/red]")
        else:
            # Check if transcription already exists
            if self.transcript_manager.check_existing_transcripts(file_path):
                console.print(f"[yellow]Skipping transcription for {file_path.name} - already exists[/yellow]")
                return
            self._process_single_file(file_path)

    def _process_single_file(self, file_path: Path) -> None:
        """Process a single audio file or split"""
        # Get file size
        file_size = self.audio_processor.get_file_size_mb(file_path)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            try:
                # Transcribe
                task_id = progress.add_task(
                    description=f"Transcribing {file_path.name} ({file_size:.2f} MB)...",
                    total=None
                )
                text, metadata = self.transcription_service.transcribe_file(file_path)

                # Save results
                txt_path, json_path = self.transcript_manager.save_transcript(
                    text, metadata, file_path
                )

                # Clean transcript
                progress.update(task_id, description=f"Cleaning transcript for {file_path.name}...")
                clean_path = self.transcript_cleaner.clean_transcript(txt_path)

                console.print(f"[green]Successfully processed {file_path.name}[/green]")
                console.print(f"[blue]Transcript saved to: {txt_path}[/blue]")
                console.print(f"[blue]Cleaned transcript saved to: {clean_path}[/blue]")
                console.print(f"[blue]Metadata saved to: {json_path}[/blue]\n")

            except Exception as e:
                logger.error(f"Error processing {file_path}: {str(e)}")
                console.print(f"[red]Error processing {file_path}: {str(e)}[/red]")
                raise

    def reclean_all_transcripts(self) -> None:
        """Re-clean all existing transcripts that don't have a clean version"""
        console.print("[cyan]Starting to clean all transcripts...[/cyan]")

        # Get all .txt files that are not .clean.txt and sort them
        transcript_files = sorted([
            f for f in self.paths.TRANSCRIPTS.glob("*.txt")
            if not f.name.endswith('.clean.txt')
        ])

        if not transcript_files:
            console.print("[yellow]No transcripts found to clean[/yellow]")
            return

        console.print(f"[cyan]Found {len(transcript_files)} transcripts to process[/cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task_id = progress.add_task(description="Cleaning transcripts...", total=len(transcript_files))

            for transcript_file in transcript_files:
                try:
                    progress.update(task_id, description=f"Cleaning {transcript_file.name}...")
                    clean_path = self.transcript_cleaner.clean_transcript(transcript_file)
                    console.print(f"[yellow]Skipping {transcript_file.name} - clean version already exists[/yellow]")
                    console.print(f"[blue]Clean version location: {clean_path}[/blue]")
                except Exception as e:
                    logger.error(f"Failed to clean {transcript_file}: {e}")
                    console.print(f"[red]Failed to clean {transcript_file}: {str(e)}[/red]")
                finally:
                    progress.advance(task_id)

        console.print("[green]Completed transcript cleaning process[/green]")

def main():
    """Main entry point"""
    console.print(Panel.fit(
        "Audio Transcription Pipeline (using OpenAI Whisper)",
        style="bold magenta"
    ))

    try:
        pipeline = AudioTranscriptionPipeline()

        # Process files in original directory first
        original_files = [
            f for f in pipeline.paths.ORIGINAL.iterdir()
            if f.suffix.lower() in pipeline.config.SUPPORTED_FORMATS
        ]

        if not original_files:
            console.print("[yellow]No mp3 or wav files found in original directory[/yellow]")
            return

        console.print(f"[cyan]Found {len(original_files)} audio files to process[/cyan]")

        # Process one file at a time
        for index, file in enumerate(original_files, 1):
            try:
                console.print(f"\n[bold cyan]Processing file {index}/{len(original_files)}: {file.name}[/bold cyan]")

                # Process current file
                pipeline.process_file(file)

                # Verify transcription files were created
                expected_txt = list(pipeline.paths.TRANSCRIPTS.glob(f"{file.stem}*.txt"))
                expected_json = list(pipeline.paths.TRANSCRIPTS.glob(f"{file.stem}*.json"))

                if not expected_txt or not expected_json:
                    raise RuntimeError(f"Transcription files not found for {file.name}")

                console.print(f"[green]✓ Successfully completed processing {file.name}[/green]")
                console.print("=" * 50)  # Visual separator between files

            except Exception as e:
                console.print(f"[red]Failed to process {file.name}: {str(e)}[/red]")
                logger.error(f"Failed to process {file.name}: {e}")
                console.print("=" * 50)  # Visual separator between files
                continue

        # After processing all audio files, clean all transcripts
        pipeline.reclean_all_transcripts()

    except Exception as e:
        console.print(f"[red bold]Fatal error: {str(e)}[/red bold]")
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()
