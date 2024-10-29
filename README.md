# AudioScribe - Transcribe & Refine

Transform your audio files into clear, coherent text with AudioScribe. Leveraging the power of OpenAI's Whisper model, AudioScribe offers seamless transcription of audio files with detailed logging, visual feedback, and error handling. Whether you're handling lengthy recordings or brief sound bites, AudioScribe splits, transcribes, and refines your audio with ease, ensuring that each transcription is as accurate and readable as possible.

## Features

- Transcribe MP3 and WAV audio files using OpenAI's Whisper model
- Object-oriented architecture for better code organization and maintainability
- Automatic handling of large files with smart splitting functionality
- Rich console interface with progress indicators and colored output
- Detailed error handling and logging with retry mechanisms
- Secure API key management using environment variables
- Multiple output formats:
  - JSON files with detailed transcription metadata
  - Raw text transcriptions
  - Cleaned and refined transcriptions using GPT-3.5-turbo
- Skip processing of already transcribed files
- Support for custom ffmpeg and ffprobe paths
- Automatic merging of split transcripts
- Batch transcript cleaning functionality
- Comprehensive test suite with pytest

## Prerequisites

Before you begin, ensure you have met the following requirements:

- Python 3.13 or higher
- `uv` package manager installed (for virtual environment and dependency management)
- An OpenAI API key
- ffmpeg and ffprobe installed (paths can be configured via environment variables)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AudioScribe.git
   cd AudioScribe
   ```

2. Create and activate a virtual environment using `uv`:
   ```bash
   # Create virtual environment
   uv venv
   # Activate virtual environment
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. Install the package and development dependencies:
   ```bash
   # Install the package in development mode
   uv pip install -e .

   # Install development dependencies
   uv add --dev pytest pytest-cov pyright ruff
   ```

4. Create a `.env` file in the project root by copying the example:
   ```bash
   cp .env.example .env
   ```

5. Update the `.env` file with your configuration:
   ```
   OPENAI_API_KEY=your_api_key_here
   FFMPEG_PATH=/path/to/ffmpeg
   FFPROBE_PATH=/path/to/ffprobe
   ```

## Usage

1. Place your MP3 or WAV files in the `data/original` directory.

2. Run the transcription script:
   ```bash
   python -m audioscribe.main
   ```

3. The transcribed text and additional information will be saved in three formats for each audio file:
   - `<filename>.json`: Detailed JSON output with all transcription information
   - `<filename>.txt`: Plain text transcription
   - `<filename>.clean.txt`: Cleaned up version of the transcription for better coherence

4. For large audio files (>25MB):
   - The script will automatically split them into smaller chunks for processing
   - Each chunk will be processed individually
   - The transcripts will be automatically merged after processing

## Testing

The project includes a comprehensive test suite using pytest. To run the tests:

```bash
# Run all tests with verbose output and duration info
pytest -v --durations=5

# Run tests with coverage report
pytest -v --durations=0 --cov --cov-report=xml

# Run linting and formatting checks
uvx ruff check .
uvx ruff format .

# Run type checking
uv run pyright .

# Run specific test file
pytest tests/test_audio.py
```

## Project Structure

```
AudioScribe/
├── data/
│   ├── original/      # Place input audio files here
│   ├── splits/        # Temporary storage for split audio files
│   └── transcripts/   # Output directory for transcriptions
├── src/
│   └── audioscribe/   # Main package directory
│       ├── __init__.py
│       ├── audio.py           # Audio processing functionality
│       ├── config.py          # Configuration management
│       ├── main.py           # Main entry point
│       ├── pipeline.py       # Transcription pipeline
│       ├── transcript.py     # Transcript management
│       └── transcription.py  # OpenAI API interaction
├── tests/
│   ├── conftest.py           # Test fixtures
│   ├── test_audio.py        # Audio processing tests
│   ├── test_transcript.py   # Transcript management tests
│   └── test_transcription.py # Transcription service tests
├── .env.example             # Example environment variables
├── .gitignore
├── LICENSE
├── README.md
└── pyproject.toml          # Project metadata and dependencies
```

## How it works

1. The script initializes the OpenAI client with proper error handling and extended timeout configurations.
2. It validates the OpenAI API key before proceeding with any transcriptions.
3. It scans the `data/original` directory for MP3 and WAV files.
4. For each audio file in the original directory:
   a. It checks if the file has already been processed. If so, it skips to the next file.
   b. If the file is larger than 25MB:
      - It's automatically split into smaller chunks and saved in the `data/splits` directory
      - Each chunk is processed individually
   c. Each chunk (or the whole file if it's small enough) is sent to the OpenAI API for transcription using the Whisper model.
   d. The script uses retry logic with exponential backoff to handle potential temporary failures.
   e. A progress bar is displayed during the transcription process, updating for each chunk in large files.
   f. The API transcribes the audio and returns the result in a detailed JSON format.
   g. The script saves the transcribed text and additional information in JSON and TXT formats.
   h. The script then uses GPT-3.5-turbo to clean up the transcription and save it as a separate file.
5. After processing all files:
   - The script runs a cleaning pass on any transcripts that don't have clean versions
   - All split transcripts are automatically merged into complete files
   - Both raw and cleaned transcripts are merged separately

## Error Handling

The script includes comprehensive error handling:

- API authentication and rate limit handling
- File system operation error management
- Transcription process error recovery
- Automatic retries with exponential backoff
- Detailed error logging and user feedback
- Rich console output for better visibility

## Customization

You can customize the script by modifying the following classes:

- `AudioConfig`: Adjust file size limits, supported formats, and paths
- `TranscriptionService`: Change the Whisper model or API settings
- `TranscriptCleaner`: Modify the cleaning prompt or model
- `AudioTranscriptionPipeline`: Adjust the processing workflow

## Troubleshooting

If you encounter issues:

1. Verify your OpenAI API key in the `.env` file
2. Check that audio files are in supported formats (MP3 or WAV)
3. Ensure ffmpeg and ffprobe paths are correctly set in `.env`
4. Review console output for error messages
5. Check available disk space for split files
6. Verify OpenAI API rate limits and credits
7. Run the test suite to verify system functionality


## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgements

- OpenAI for the Whisper model and GPT-3.5-turbo
- Rich library for terminal formatting
- python-dotenv for environment management
- FFmpeg for audio processing
- pytest for testing framework
- uv for package management and virtual environments
- ruff for linting and formatting
- pyright for type checking
