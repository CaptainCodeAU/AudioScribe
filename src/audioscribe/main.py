"""Main module for AudioScribe."""

import logging

from rich.console import Console
from rich.panel import Panel

from .pipeline import AudioTranscriptionPipeline

# Initialize Rich console for better output formatting
console = Console()
logger = logging.getLogger(__name__)


def main() -> None:
    """Main entry point for the AudioScribe package."""
    console.print(
        Panel.fit("Audio Transcription Pipeline (using OpenAI Whisper)", style="bold magenta")
    )

    try:
        pipeline = AudioTranscriptionPipeline()

        # Process files in original directory first
        original_files = [
            f
            for f in pipeline.paths.ORIGINAL.iterdir()
            if f.suffix.lower() in pipeline.config.SUPPORTED_FORMATS
        ]

        if not original_files:
            console.print("[yellow]No mp3 or wav files found in original directory[/yellow]")
            return

        console.print(f"[cyan]Found {len(original_files)} audio files to process[/cyan]")

        # Process one file at a time
        for index, file in enumerate(original_files, 1):
            try:
                console.print(
                    f"\n[bold cyan]Processing file {index}/{len(original_files)}: {file.name}[/bold cyan]"
                )

                # Process current file
                pipeline.process_file(file)
                console.print(f"[green]✓ Successfully completed processing {file.name}[/green]")
                console.print("=" * 50)  # Visual separator between files

            except Exception as e:
                console.print(f"[red]Failed to process {file.name}: {e!s}[/red]")
                logger.error(f"Failed to process {file.name}: {e}")
                console.print("=" * 50)  # Visual separator between files
                continue

        # Merge all transcript files
        pipeline.transcript_manager.merge_transcripts()

        # Verify merged transcription files after merging
        for file in original_files:
            base_name = pipeline.transcript_manager._get_base_filename(file)
            txt_path = pipeline.paths.TRANSCRIPTS / f"{base_name}.txt"
            json_path = pipeline.paths.TRANSCRIPTS / f"{base_name}.json"
            clean_txt_path = pipeline.paths.TRANSCRIPTS / f"{base_name}.clean.txt"

            if not (txt_path.exists() and json_path.exists() and clean_txt_path.exists()):
                missing_files = []
                if not txt_path.exists():
                    missing_files.append(str(txt_path))
                if not json_path.exists():
                    missing_files.append(str(json_path))
                if not clean_txt_path.exists():
                    missing_files.append(str(clean_txt_path))
                raise RuntimeError(f"Missing merged transcription files for {file.name}: {', '.join(missing_files)}")

            console.print(f"[green]✓ Successfully verified merged transcripts for {file.name}[/green]")

    except Exception as e:
        console.print(f"[red bold]Fatal error: {e!s}[/red bold]")
        logger.error(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
