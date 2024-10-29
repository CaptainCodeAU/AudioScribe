"""Pipeline module for orchestrating the audio transcription process."""

import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .audio import AudioProcessor
from .config import AudioConfig, ProjectPaths
from .transcript import TranscriptManager
from .transcription import TranscriptionService, TranscriptCleaner

# Initialize Rich console for better output formatting
console = Console()
logger = logging.getLogger(__name__)


class AudioTranscriptionPipeline:
    """Main pipeline orchestrating the entire transcription process."""

    def __init__(self):
        self.config = AudioConfig()
        self.paths = ProjectPaths()
        self.audio_processor = AudioProcessor(self.config)
        self.transcription_service = TranscriptionService()
        self.transcript_manager = TranscriptManager(self.paths.TRANSCRIPTS)
        self.transcript_cleaner = TranscriptCleaner(self.transcription_service.client)
        self.logger = logging.getLogger(__name__)

    def process_file(self, file_path: Path) -> None:
        """Process a single audio file."""
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
                        console.print(
                            f"[yellow]Skipping transcription for {split_file.name} - already exists[/yellow]"
                        )
                        continue
                    self._process_single_file(split_file)
                except Exception as e:
                    logger.error(f"Failed to process split file {split_file}: {e}")
                    console.print(f"[red]Failed to process split file {split_file}: {e}[/red]")
        else:
            # Check if transcription already exists
            if self.transcript_manager.check_existing_transcripts(file_path):
                console.print(
                    f"[yellow]Skipping transcription for {file_path.name} - already exists[/yellow]"
                )
                return
            self._process_single_file(file_path)

    def _process_single_file(self, file_path: Path) -> None:
        """Process a single audio file or split."""
        # Get file size
        file_size = self.audio_processor.get_file_size_mb(file_path)

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            try:
                # Transcribe
                task_id = progress.add_task(
                    description=f"Transcribing {file_path.name} ({file_size:.2f} MB)...", total=None
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
                logger.error(f"Error processing {file_path}: {e!s}")
                console.print(f"[red]Error processing {file_path}: {e!s}[/red]")
                raise

    def reclean_all_transcripts(self) -> None:
        """Re-clean all existing transcripts that don't have a clean version."""
        console.print("[cyan]Starting to clean all transcripts...[/cyan]")

        # Get all .txt files that are not .clean.txt and sort them
        transcript_files = sorted(
            [f for f in self.paths.TRANSCRIPTS.glob("*.txt") if not f.name.endswith(".clean.txt")]
        )

        if not transcript_files:
            console.print("[yellow]No transcripts found to clean[/yellow]")
            return

        console.print(f"[cyan]Found {len(transcript_files)} transcripts to process[/cyan]")

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task_id = progress.add_task(
                description="Cleaning transcripts...", total=len(transcript_files)
            )

            for transcript_file in transcript_files:
                try:
                    progress.update(task_id, description=f"Cleaning {transcript_file.name}...")
                    clean_path = self.transcript_cleaner.clean_transcript(transcript_file)
                    console.print(
                        f"[yellow]Skipping {transcript_file.name} - clean version already exists[/yellow]"
                    )
                    console.print(f"[blue]Clean version location: {clean_path}[/blue]")
                except Exception as e:
                    logger.error(f"Failed to clean {transcript_file}: {e}")
                    console.print(f"[red]Failed to clean {transcript_file}: {e!s}[/red]")
                finally:
                    progress.advance(task_id)

        console.print("[green]Completed transcript cleaning process[/green]")
