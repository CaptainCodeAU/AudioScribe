# AudioScribe - Transcribe & Refine

Transform your audio files into clear, coherent text with AudioScribe. Leveraging the power of OpenAI's Whisper model, AudioScribe offers seamless transcription of MP3 and WAV files with detailed logging, visual feedback, and error handling. Whether you're handling lengthy recordings or brief sound bites, AudioScribe splits, transcribes, and refines your audio with ease, ensuring that each transcription is as accurate and readable as possible. From detailed JSON outputs to clean text files, AudioScribe is your go-to tool for converting sound into script with precision.

## Features

- Transcribe MP3 and WAV audio files using OpenAI's Whisper model
- Process all audio files in the `data/original` directory
- Automatically handle split files in the `data/splits` directory
- Secure API key management using environment variables
- Save transcription results in JSON and TXT formats
- Clean up transcriptions using gpt-4o-mini for better coherence
- Visual progress indicators and colored console output
- Detailed error handling and logging
- Efficient handling of large audio files with automatic chunking
- Retry logic with exponential backoff for improved reliability
- Support for custom ffmpeg and ffprobe paths
- Skip processing of already transcribed files and existing clean versions
- Process files from both original and splits directories sequentially
- API key validation before processing

## Prerequisites

Before you begin, ensure you have met the following requirements:

- Python 3.7 or higher
- An OpenAI API key
- ffmpeg and ffprobe installed (paths can be configured in the script)

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/mp3-to-text-openai.git
   cd mp3-to-text-openai
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root and add your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

4. Update the `FFMPEG_PATH` and `FFPROBE_PATH` variables in the `transcribe_audio.py` script to point to your ffmpeg and ffprobe installations.

## Usage

1. Place your MP3 or WAV files in the `data/original` directory.

2. Run the transcription script:
   ```
   python transcribe_audio.py
   ```

3. The transcribed text and additional information will be saved in three formats for each audio file:
   - `<filename>.json`: Detailed JSON output with all transcription information
   - `<filename>.txt`: Plain text transcription
   - `<filename>.clean.txt`: Cleaned up version of the transcription for better coherence

4. For large audio files (>25MB), the script will automatically split them into smaller chunks for processing.

5. Detailed output, including progress information, will be displayed in the console.

## How it works

1. The script initializes the OpenAI client with proper error handling and extended timeout configurations.
2. It validates the OpenAI API key before proceeding with any transcriptions.
3. It scans the `data/original` directory for MP3 and WAV files.
4. For each audio file in the original directory:
   a. It checks if the file has already been processed. If so, it skips to the next file.
   b. If the file is larger than 25MB, it's automatically split into smaller chunks and saved in the `data/splits` directory.
   c. Each chunk (or the whole file if it's small enough) is sent to the OpenAI API for transcription using the Whisper model.
   d. The script uses retry logic with exponential backoff to handle potential temporary failures.
   e. A progress bar is displayed during the transcription process, updating for each chunk in large files.
   f. The API transcribes the audio and returns the result in a detailed JSON format.
   g. For large files, the script combines the transcriptions from all chunks.
   h. The script saves the transcribed text and additional information in JSON and TXT formats.
   i. The script then uses gpt-4o-mini to clean up the transcription and save it as a separate file.
5. After processing all files in the original directory, the script processes any remaining MP3 files in the `data/splits` directory.
6. The script then processes any text files in the `data/splits` directory, cleaning up transcriptions that don't have a clean version yet.
7. Finally, it processes optional text files in the `data/optional_text` directory.
8. The script skips creating clean versions for files that already have them.
9. Detailed output, including a transcription summary, is displayed in the console throughout the process.

## File structure

- `transcribe_audio.py`: Main script for audio transcription
- `requirements.txt`: List of Python package dependencies
- `.env`: File to store the OpenAI API key (not included in the repository)
- `data/original/`: Directory containing input audio files (MP3 or WAV)
- `data/splits/`: Directory containing split audio files (for large files)
- `data/optional_text/`: Directory containing optional text files for processing
- `<filename>.json`: JSON output file containing detailed transcription information
- `<filename>.txt`: Plain text output file containing the transcribed text
- `<filename>.clean.txt`: Cleaned up version of the transcription for better coherence


---
---


# MP3 to Text Transcription with OpenAI - Charts

This file contains mermaid charts explaining various aspects of the project.

## Project Structure

```mermaid
graph TD
    A[Project Root] --> B[transcribe_audio.py]
    A --> C[requirements.txt]
    A --> D[.env]
    A --> E[data/]
    E --> F[original/]
    E --> G[splits/]
    E --> H[optional_text/]
    F --> I[Input MP3/WAV files]
    G --> J[Split audio files]
    G --> K[Transcription files]
    H --> L[Optional text files]
    K --> M[.json files]
    K --> N[.txt files]
    K --> O[.clean.txt files]
    A --> P[.gitignore]
    A --> Q[LICENSE]
```

## Audio Processing Workflow

```mermaid
graph TD
    A[Start] --> B{File > 25MB?}
    B -- Yes --> C[Split Audio]
    B -- No --> D[Transcribe Audio]
    C --> D
    D --> E[Save JSON Transcription]
    D --> F[Save TXT Transcription]
    E --> G{Clean Version Exists?}
    F --> G
    G -- No --> H[Clean Transcription]
    G -- Yes --> I[Skip Cleaning]
    H --> J[Save Clean TXT]
    I --> K[End]
    J --> K
```

## File Processing Decision Tree

```mermaid
graph TD
    A[Input File] --> B{Transcription Exists?}
    B -- Yes --> C{Clean Version Exists?}
    B -- No --> D[Process Audio File]
    C -- Yes --> E[Skip Processing]
    C -- No --> F[Clean Transcription]
    D --> G[Transcribe and Save]
    G --> F
    F --> H[Save Clean Version]
    H --> I[End]
    E --> I
```

## OpenAI API Interaction

```mermaid
sequenceDiagram
    participant Script
    participant OpenAIClient
    participant WhisperAPI
    participant GPT4oMiniAPI

    Script->>OpenAIClient: Initialize client
    Script->>OpenAIClient: Validate API key
    loop For each audio chunk
        Script->>OpenAIClient: Send audio chunk
        OpenAIClient->>WhisperAPI: Transcribe audio
        WhisperAPI-->>OpenAIClient: Return transcription
        OpenAIClient-->>Script: Return transcription
    end
    Script->>Script: Combine chunk transcriptions (if split)
    Script->>Script: Save transcription (JSON & TXT)
    Script->>OpenAIClient: Send transcription for cleaning
    OpenAIClient->>GPT4oMiniAPI: Clean transcription
    GPT4oMiniAPI-->>OpenAIClient: Return cleaned text
    OpenAIClient-->>Script: Return cleaned text
    Script->>Script: Save cleaned transcription
```

These charts provide a visual representation of the project structure, workflow, decision-making process, and API interactions in the MP3 to Text Transcription project.



### Main Execution

The `main()` function orchestrates the entire process, including:

1. Initializing the OpenAI client
2. Validating the OpenAI API key
3. Processing all MP3 and WAV files in the `data/original` directory
4. Splitting audio files if necessary
5. Transcribing the audio files
6. Saving transcriptions in JSON and TXT formats
7. Cleaning up transcriptions and saving them as separate files
8. Processing existing transcriptions without clean versions
9. Skipping files that have already been processed or have existing clean versions

## API Key Validation

The script now includes an API key validation step:

- Before processing any files, the script attempts to list available models using the provided API key.
- If the API key is invalid or there are any authentication issues, the script will raise an error and stop execution.
- This ensures that potential API key issues are caught early in the process, saving time and preventing unnecessary processing attempts.

## Error Handling

The script includes comprehensive error handling:

- Client initialization errors
- API key validation errors
- File not found errors
- Transcription process errors
- File saving errors
- Audio splitting errors
- Transcription cleaning errors
- Improved handling of split file transcription failures:
  - Each chunk is now processed independently
  - If a chunk fails to transcribe, the script logs the error and continues with the next chunk
  - The script ensures at least one chunk is successfully transcribed before combining results
  - If all chunks fail, an informative exception is raised
- Chunk size verification to prevent processing chunks larger than the API limit
- Detailed logging of chunk transcription attempts and results
- Specific handling for OpenAI API errors:
  - Authentication errors
  - Rate limit errors
  - General API errors

Each error is logged and displayed to the user with appropriate context, including specific error messages from the OpenAI API when available.

## Retry Mechanism

The script implements a robust retry mechanism to handle temporary failures:

- The entire file transcription process can be retried up to 3 times
- Each chunk transcription attempt uses exponential backoff for retries
- Different wait times are implemented based on the type of error:
  - Longer waits for rate limit errors (60 seconds base, doubling each retry)
  - Medium waits for general API errors (10 seconds base, doubling each retry)
  - Shorter waits for unexpected errors (5 seconds base, doubling each retry)
- A delay of 10 seconds is added between chunk transcriptions to avoid rate limiting issues
- If all retries fail, the script raises an informative exception and moves on to the next file

This retry mechanism significantly improves the script's resilience to temporary network issues, API failures, and rate limiting.

## Visual Output

The script uses the Rich library to provide a visually appealing console output:

- Colored text for different types of information
- Progress bar for the transcription process
- Panels for important information
- Formatted display of transcription summary

## Customization

You can customize the script by modifying the following:

- Change the `model` parameter in the `transcribe_audio_chunk` function to use a different OpenAI model.
- Adjust the timeout settings in the `get_openai_client` function to accommodate your specific needs.
- Modify the output formats or add additional formats in the `save_transcription` function.
- Adjust the `MAX_SPLIT_SIZE_MB` and `MAX_SPLIT_DURATION` constants to change the thresholds for splitting audio files.
- Modify the cleaning prompt or model in the `clean_transcription` function to adjust the coherence improvement process.
- Adjust retry attempts and wait times in the `transcribe_audio_chunk` and `transcribe_audio` functions to fine-tune the retry mechanism.

## Troubleshooting

If you encounter issues:

1. Ensure your OpenAI API key is correctly set in the `.env` file and is valid.
2. Check that your input audio files are valid MP3 or WAV files and are placed in the `data/original` directory.
3. Verify that you have sufficient credits in your OpenAI account.
4. Check the console output and log files for any error messages. The script now provides more detailed error information, especially for API-related issues.
5. Ensure that the ffmpeg and ffprobe paths are correctly set in the script.
6. For large files, make sure you have enough disk space for temporary split files.
7. If you're experiencing frequent failures, try adjusting the retry settings or adding longer delays between API calls.
8. If you encounter persistent rate limit errors, you may need to reduce the frequency of API calls or contact OpenAI to increase your rate limits.

## Contributing

Contributions to this project are welcome. Please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Make your changes and commit them with clear, descriptive messages.
4. Push your changes to your fork.
5. Submit a pull request with a clear description of your changes.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Acknowledgements

- [OpenAI](https://www.openai.com) for providing the Whisper model and gpt-4o-mini API
- [python-dotenv](https://github.com/theskumar/python-dotenv) for environment variable management
- [Rich](https://github.com/Textualize/rich) for beautiful terminal formatting
- [httpx](https://www.python-httpx.org/) for improved HTTP client functionality
- [FFmpeg](https://ffmpeg.org/) for audio file manipulation
