# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2024-11-30

### Changed
- Updated to use latest OpenAI models for better accuracy
  - Now uses `whisper-large-v3` as default transcription model
  - Now uses `gpt-4-0125-preview` as default transcript cleaning model
- Added automatic fallback mechanism to more economical models if high-quality models fail
  - Falls back to `whisper-1` for transcription
  - Falls back to `gpt-3.5-turbo-0125` for transcript cleaning

## [0.2.0] - 2024-03-19

### Added
- Automatic conversion of M4A files to MP3 format using ffmpeg
- Skip conversion if MP3 file already exists

### Changed
- Enhanced AudioProcessor class with M4A to MP3 conversion capabilities
- Updated split_audio method to handle M4A files through conversion

## [0.1.0] - Initial Release

### Added
- Initial release of AudioScribe
- Support for MP3 and WAV audio files
- Audio file splitting functionality
- Integration with OpenAI Whisper API for transcription
- Basic transcript management and merging capabilities
