import os
import argparse
from pathlib import Path
from audio_separation import AudioSeparator
from forced_alignment import LyricsAligner
from video_generator import KaraokeVideoGenerator

def find_input_files(input_dir):
    """Find audio and lyrics files in the input directory"""
    input_path = Path(input_dir)
    audio_extensions = ('.mp3', '.wav', '.flac')
    audio_file = None
    lyrics_file = None
    
    for file in input_path.iterdir():
        if file.suffix.lower() in audio_extensions:
            audio_file = file
        elif file.suffix.lower() == '.txt':
            lyrics_file = file
            
    return audio_file, lyrics_file

def run_test_mode(input_dir, output_dir):
    """Run only the alignment and test video generation"""
    # Get paths
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    base_name = input_path.name
    
    audio_path = input_path / 'song_vocals.wav'
    lyrics_path = input_path / 'lyrics.txt'
    
    # Initialize components
    aligner = LyricsAligner(str(output_path))
    video_gen = KaraokeVideoGenerator(str(output_path))
    
    # Perform alignment
    print(f"Aligning lyrics with audio...")
    alignment_path = output_path / 'song_vocals_alignment.json'
    alignment_path.parent.mkdir(parents=True, exist_ok=True)
    alignment_data = aligner.run_asr(str(audio_path), str(lyrics_path))
    
    # Generate test video
    print(f"Generating test video...")
    video_path = video_gen.test_alignment(str(audio_path), str(alignment_path), base_name)
    
    print(f"Test process completed successfully!")
    print(f"Alignment file: {alignment_path}")
    print(f"Test video: {video_path}")

def run_full_process(input_dir, output_dir):
    """Run the complete karaoke video generation process"""
    try:
        # Find input files
        audio_file, lyrics_file = find_input_files(input_dir)
        if not audio_file or not lyrics_file:
            print("Error: Could not find both audio and lyrics files in input directory")
            return
        
        # Initialize components
        separator = AudioSeparator(str(output_dir))
        aligner = LyricsAligner(str(output_dir))
        video_gen = KaraokeVideoGenerator(str(output_dir))
        
        # Process files
        print("Separating vocals from instrumental...")
        vocal_path, instrumental_path = separator.separate(str(audio_file))
        
        print("Aligning lyrics with audio...")
        alignment_data = aligner.run_asr(vocal_path, str(lyrics_file))
        
        print("Generating karaoke video...")
        output_name = audio_file.stem
        video_path = video_gen.generate(instrumental_path, alignment_data, output_name)
        
        print(f"Karaoke video generated successfully: {video_path}")
        
    except Exception as e:
        print(f"Error during processing: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Generate karaoke video from audio and lyrics')
    parser.add_argument('--input_dir', required=True, help='Directory containing audio and lyrics files')
    parser.add_argument('--output_dir', required=True, help='Directory for output files')
    parser.add_argument('--test_only', action='store_true', help='Only run alignment and test video generation')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    if args.test_only:
        run_test_mode(args.input_dir, args.output_dir)
    else:
        run_full_process(args.input_dir, args.output_dir)

if __name__ == "__main__":
    main() 