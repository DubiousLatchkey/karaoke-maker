# Karaoke Video Generator

This Python project automatically generates karaoke videos from audio files and lyrics. It performs the following steps:

1. Separates vocals from instrumental using HTDemucs
2. Performs forced alignment between lyrics and audio
3. Generates a karaoke video with timed lyrics

## Requirements

- Python 3.8 or higher
- FFmpeg installed on your system
- Required Python packages (install using `pip install -r requirements.txt`)

## Project Structure

- `main.py`: Main orchestration script
- `audio_separation.py`: Handles vocal/instrumental separation
- `forced_alignment.py`: Manages lyrics alignment with audio
- `video_generator.py`: Creates the final karaoke video

## Usage

1. Place your audio file and lyrics text file in the input directory
2. Run the main script:
   ```bash
   python main.py --input_dir /path/to/input --output_dir /path/to/output
   ```

## Input Format

- Audio file: Supported formats include MP3, WAV, FLAC
- Lyrics file: Plain text file with one line per lyric line

## Output

The program will generate:
- Separated vocal and instrumental tracks
- A karaoke video with timed lyrics


Download torch and torchaudio with the website (pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118) for gpu