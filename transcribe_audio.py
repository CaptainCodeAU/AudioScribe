import os
import math
import json
import logging
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.audio import Transcription
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# Initialize Rich console for better output formatting
console = Console()

# Constants for audio splitting and processing
MAX_SPLIT_SIZE_MB = 10  # Maximum size of each split in MB
MAX_SPLIT_DURATION = 600  # Maximum duration of each split in seconds (10 minutes)
MAX_FILE_SIZE = 25 * 1024 * 1024  # Maximum file size for OpenAI API (25 MB)

# Set FFMPEG and FFPROBE paths
FFMPEG_PATH = "/Users/admin/Documents/apps/ffmpeg"
FFPROBE_PATH = "/Users/admin/Documents/apps/ffprobe"

# Add the directory containing ffmpeg and ffprobe to the system PATH
os.environ["PATH"] = f"/Users/admin/Documents/apps:{os.environ['PATH']}"

# Define the directories for original and split audio files
ORIGINAL_AUDIO_DIR = Path("./data/original")
SPLIT_AUDIO_DIR = Path("./data/splits")
OPTIONAL_TEXT_DIR = Path("./data/optional_text")

# Create directories if they don't exist
ORIGINAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
SPLIT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
OPTIONAL_TEXT_DIR.mkdir(parents=True, exist_ok=True)


def get_openai_client():
    """
    Initialize and return an OpenAI client with specified settings.

    Returns:
        OpenAI: An initialized OpenAI client object.

    Raises:
        Exception: If initialization fails.
    """
    try:
        return OpenAI(
            api_key=os.environ.get("OPENAI_API_KEY"),
            max_retries=5,
            timeout=httpx.Timeout(600.0, read=300.0, write=10.0, connect=5.0),
        )
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        raise


def split_audio(
    file_path: Path,
    max_size_mb: int = MAX_SPLIT_SIZE_MB,
    max_duration: int = MAX_SPLIT_DURATION,
):
    """
    Split an audio file into smaller segments based on size and duration constraints.

    Args:
        file_path (Path): Path to the input audio file.
        max_size_mb (int): Maximum size of each split in MB.
        max_duration (int): Maximum duration of each split in seconds.

    Returns:
        list: List of Path objects representing the split audio files.
    """
    output_template = SPLIT_AUDIO_DIR / f"{file_path.stem}_part%03d.mp3"

    # Get the bitrate and duration of the input file using ffprobe
    probe_cmd = [
        FFPROBE_PATH,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=bit_rate",
        "-of",
        "json",
        str(file_path),
    ]
    probe_output = json.loads(subprocess.check_output(probe_cmd).decode())

    bitrate = int(probe_output["streams"][0]["bit_rate"])
    total_duration = float(probe_output["format"]["duration"])

    # Calculate segment duration based on max size and bitrate, and max duration
    size_based_duration = (max_size_mb * 8 * 1024 * 1024) / bitrate
    segment_duration = min(size_based_duration, max_duration)

    # Calculate the number of segments
    num_segments = math.ceil(total_duration / segment_duration)

    # Prepare ffmpeg command for splitting the audio
    cmd = [
        FFMPEG_PATH,
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

    # Run the ffmpeg command to split the audio
    subprocess.run(cmd, check=True)

    # Return list of created files
    split_files = sorted(SPLIT_AUDIO_DIR.glob(f"{file_path.stem}_part*.mp3"))
    for split_file in split_files:
        console.print(f"[bold magenta]Created split file:[/bold magenta] {split_file}")
    return split_files


def transcribe_audio_chunk(client: OpenAI, file_path: Path, retries: int = 5) -> Transcription:
    """
    Transcribe an audio chunk using OpenAI's Whisper model with retry logic.

    Args:
        client (OpenAI): An initialized OpenAI client object.
        file_path (Path): Path to the audio file to transcribe.
        retries (int): Number of retries for the transcription.

    Returns:
        Transcription: OpenAI Transcription object containing the transcription results.

    Raises:
        Exception: If transcription fails after all retries.
    """
    for attempt in range(retries):
        try:
            with file_path.open("rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, response_format="verbose_json"
                )
            return response
        except Exception as e:
            if attempt < retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Transcription attempt {attempt + 1} failed. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to transcribe audio after {retries} attempts: {e}")
                raise


def transcribe_audio(client: OpenAI, file_path: Path) -> Transcription:
    """
    Transcribe an audio file using OpenAI's Whisper model, with support for chunking.

    Args:
        client (OpenAI): An initialized OpenAI client object.
        file_path (Path): Path to the audio file to transcribe.

    Returns:
        Transcription: OpenAI Transcription object containing the transcription results.

    Raises:
        Exception: If transcription fails.
    """
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            console.print(f"[bold yellow]File size exceeds 25MB. Splitting into chunks...[/bold yellow]")
            chunks = split_audio(file_path)
            transcriptions = []

            with Progress() as progress:
                task = progress.add_task(f"[cyan]Transcribing {file_path.name}...", total=len(chunks))

                for chunk in chunks:
                    try:
                        chunk_transcription = transcribe_audio_chunk(client, chunk)
                        transcriptions.append(chunk_transcription)
                    except Exception as e:
                        logger.error(f"Failed to transcribe chunk {chunk}: {e}")
                    finally:
                        progress.update(task, advance=1)

            if not transcriptions:
                raise Exception("All chunks failed to transcribe")

            # Combine transcriptions
            combined_transcription = Transcription(
                text=" ".join(t.text for t in transcriptions),
                segments=[seg for t in transcriptions for seg in t.segments],
                language=transcriptions[0].language,
            )
            return combined_transcription
        else:
            with Progress() as progress:
                task = progress.add_task(f"[cyan]Transcribing {file_path.name}...", total=1)
                response = transcribe_audio_chunk(client, file_path)
                progress.update(task, advance=1)
            return response
    except Exception as e:
        logger.error(f"Failed to transcribe audio: {e}")
        raise


def save_transcription(transcription: Transcription, base_filename: str):
    """
    Save the transcription results to JSON and TXT files.

    Args:
        transcription (Transcription): OpenAI Transcription object containing the transcription results.
        base_filename (str): Base filename for the output files.

    Returns:
        tuple: Paths to the saved JSON and TXT files.

    Raises:
        Exception: If saving fails.
    """
    try:
        # Save JSON output
        json_file = Path(f"{base_filename}.json")
        with json_file.open("w") as f:
            json.dump(transcription.model_dump(), f, indent=2)
        console.print(f"[bold blue]JSON file saved:[/bold blue] {json_file}")

        # Save TXT output
        txt_file = Path(f"{base_filename}.txt")
        with txt_file.open("w") as f:
            f.write(transcription.text)
        console.print(f"[bold green]TXT file saved:[/bold green] {txt_file}")

        return json_file, txt_file
    except Exception as e:
        logger.error(f"Failed to save transcription: {e}")
        raise


def clean_transcription(client: OpenAI, input_file: Path):
    """
    Clean up a transcription file using OpenAI's GPT model.

    Args:
        client (OpenAI): An initialized OpenAI client object.
        input_file (Path): Path to the input transcription file.

    Raises:
        Exception: If cleaning fails.
    """
    try:
        output_file = input_file.with_suffix(".clean.txt")

        # Check if clean file already exists
        if output_file.exists():
            console.print(
                f"[bold yellow]Clean version already exists:[/bold yellow] {output_file}"
            )
            return

        with input_file.open("r") as f:
            content = f.read()

        prompt = f"Remove redundant phrases and make the sentences coherent. Do not summarise the content in any way! Do not miss any point.:\n\n{content}"

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that cleans up transcriptions.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            n=1,
            temperature=0.5,
        )

        cleaned_text = response.choices[0].message.content.strip()

        with output_file.open("w") as f:
            f.write(cleaned_text)

        console.print(
            f"[bold cyan]Cleaned transcription saved:[/bold cyan] {output_file}"
        )

    except Exception as e:
        logger.error(f"Failed to clean transcription: {e}")
        raise


def process_audio_file(client: OpenAI, file_path: Path):
    """
    Process a single audio file: split if necessary, transcribe, and clean.

    Args:
        client (OpenAI): An initialized OpenAI client object.
        file_path (Path): Path to the audio file to process.
    """
    console.print(f"\n[bold cyan]Processing file:[/bold cyan] {file_path}")

    # Check if transcription already exists for the original file
    base_filename = file_path.parent / file_path.stem
    txt_file = Path(f"{base_filename}.txt")
    clean_file = Path(f"{base_filename}.clean.txt")

    if txt_file.exists() and clean_file.exists():
        console.print(
            f"[bold yellow]Skipping {file_path.name}:[/bold yellow] Transcription and clean version already exist."
        )
        console.print(f"[bold green]Existing transcription:[/bold green] {txt_file}")
        console.print(f"[bold cyan]Existing clean version:[/bold cyan] {clean_file}")
        return

    try:
        console.print(f"[bold]Transcribing {file_path.name}...[/bold]")
        transcription = transcribe_audio(client, file_path)
        console.print(
            f"[bold green]Transcription of {file_path.name} completed successfully![/bold green]"
        )

        # Save transcription
        json_file, txt_file = save_transcription(
            transcription, str(base_filename)
        )
        console.print(
            f"[bold green]Transcription saved for {file_path.name}[/bold green]"
        )

        # Clean the transcription
        console.print(f"[bold]Cleaning transcription for {file_path.name}...[/bold]")
        clean_transcription(client, txt_file)

    except Exception as e:
        console.print(
            f"[bold red]Processing of {file_path.name} failed:[/bold red] {str(e)}"
        )


def process_optional_text_files(client: OpenAI):
    """
    Process optional text files in the OPTIONAL_TEXT_DIR.

    Args:
        client (OpenAI): An initialized OpenAI client object.
    """
    console.print("\n[bold cyan]Processing optional text files:[/bold cyan]")
    optional_text_files = [
        f for f in OPTIONAL_TEXT_DIR.glob("*.txt") if not f.name.endswith(".clean.txt")
    ]

    for file in optional_text_files:
        console.print(
            f"[bold cyan]Processing optional text file:[/bold cyan] {file.name}"
        )
        clean_file = file.with_suffix(".clean.txt")

        if clean_file.exists():
            console.print(
                f"[bold yellow]Skipping {file.name}:[/bold yellow] Clean version already exists."
            )
            console.print(
                f"[bold cyan]Existing clean version:[/bold cyan] {clean_file}"
            )
            continue

        try:
            clean_transcription(client, file)
        except Exception as e:
            console.print(
                f"[bold red]Processing of optional text file {file.name} failed:[/bold red] {str(e)}"
            )


def process_split_files(client: OpenAI):
    """
    Process split text files in the SPLIT_AUDIO_DIR.

    Args:
        client (OpenAI): An initialized OpenAI client object.
    """
    console.print("\n[bold cyan]Processing split files:[/bold cyan]")
    split_files = [
        f for f in SPLIT_AUDIO_DIR.glob("*.txt") if not f.name.endswith(".clean.txt")
    ]

    for file in split_files:
        console.print(f"[bold cyan]Processing split file:[/bold cyan] {file.name}")
        clean_file = file.with_suffix(".clean.txt")

        if clean_file.exists():
            console.print(
                f"[bold yellow]Skipping {file.name}:[/bold yellow] Clean version already exists."
            )
            console.print(
                f"[bold cyan]Existing clean version:[/bold cyan] {clean_file}"
            )
            continue

        try:
            clean_transcription(client, file)
        except Exception as e:
            console.print(
                f"[bold red]Processing of split file {file.name} failed:[/bold red] {str(e)}"
            )


def main():
    """
    Main function to orchestrate the audio transcription and cleaning process.
    """
    console.print(Panel.fit("Audio Transcription with OpenAI", style="bold magenta"))

    try:
        client = get_openai_client()
        logger.info("OpenAI client initialized successfully")
        console.print("[bold green]OpenAI client initialized successfully[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return

    # Process all mp3 and wav files in the original directory
    original_audio_files = list(ORIGINAL_AUDIO_DIR.glob("*.mp3")) + list(
        ORIGINAL_AUDIO_DIR.glob("*.wav")
    )
    console.print(
        f"[bold cyan]Found {len(original_audio_files)} audio files to process in the original directory.[/bold cyan]"
    )

    for file in original_audio_files:
        process_audio_file(client, file)

    # Process any remaining mp3 files in the splits directory
    split_audio_files = list(SPLIT_AUDIO_DIR.glob("*.mp3"))
    console.print(
        f"[bold cyan]Found {len(split_audio_files)} audio files to process in the splits directory.[/bold cyan]"
    )

    for file in split_audio_files:
        process_audio_file(client, file)

    # Process split files (text files)
    process_split_files(client)

    # Process optional text files
    process_optional_text_files(client)

    console.print(
        "[bold green]All audio files, split files and optional text files processed successfully![/bold green]"
    )


if __name__ == "__main__":
    main()
