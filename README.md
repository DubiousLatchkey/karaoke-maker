# Karaoke Video Generator

This Python project automatically generates karaoke videos from audio files and lyrics. It performs the following steps:

1. Separates vocals from instrumental using HTDemucs
2. Performs forced alignment between lyrics and audio
3. Generates a karaoke video with timed lyrics

## Requirements

- Python 3.12 (Maybe other versions work but I haven't tested them)
- FFmpeg and Imagemagick installed on your system (may have to set paths LD_LIBRARY_PATH and IMAGEMAGICK_BINARY in env variables)
- Required Python packages (install using `pip install -r requirements.txt`).  Yeah they conflict.  Yeah it works.  Don't ask, just get them all installed.
- Download torch and torchaudio with the website (pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126) for gpu
- Probably something else I'm missing

## Usage

- Some of the scripts have ways to run them individually.  Otherwise, use `python karaoke_gui.py`
- Yeah I tried to make an executable.  No it didn't work.  Something about whisperx and pyinstaller idk
