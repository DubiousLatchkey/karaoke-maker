import os
import argparse
from pathlib import Path
from audio_separation import AudioSeparator
from forced_alignment import LyricsAligner
from video_generator import KaraokeVideoGenerator

def find_input_files(input_dir):
    """Find audio and lyrics files in the input directory"""
    input_path = Path(input_dir)
    audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac')
    audio_file = None
    lyrics_file = None
    
    # First look for a file named "song" with any audio extension
    for ext in audio_extensions:
        song_file = input_path / f"song{ext}"
        if song_file.exists():
            audio_file = song_file
            break
            
    # If no "song" file found, take first audio file
    if not audio_file:
        for file in input_path.iterdir():
            if file.suffix.lower() in audio_extensions:
                audio_file = file
                break
                
    # Look for lyrics file
    for file in input_path.iterdir():
        if file.suffix.lower() == '.txt':
            lyrics_file = file
            
    return audio_file, lyrics_file

def run_full_karaoke_process(input_dir, output_dir, song_name=None):
    """
    Run the complete karaoke video generation process:
    1. Vocal separation using Demucs
    2. Forced alignment with Viterbi algorithm  
    3. Karaoke video generation with synchronized lyrics
    
    Args:
        input_dir: Directory containing audio and lyrics files
        output_dir: Directory for output files
        song_name: Optional custom name for output files (defaults to audio filename)
    
    Returns:
        dict: Paths to all generated files
    """
    try:
        print("=== KARAOKE MAKER - FULL PROCESS ===\n")
        
        # Find input files
        audio_file, lyrics_file = find_input_files(input_dir)
        if not audio_file or not lyrics_file:
            print("Error: Could not find both audio and lyrics files in input directory")
            print(f"Audio file: {audio_file}")
            print(f"Lyrics file: {lyrics_file}")
            return None
        
        # Determine output name
        base_name = song_name if song_name else audio_file.stem
        print(f"Processing: {audio_file.name}")
        print(f"Lyrics: {lyrics_file.name}")
        print(f"Output name: {base_name}\n")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        print("Initializing processing components...")
        separator = AudioSeparator(str(output_path))
        aligner = LyricsAligner(str(output_path))
        video_gen = KaraokeVideoGenerator(str(output_path), resolution="360")
        
        # Step 1: Vocal Separation
        print("\n--- STEP 1: VOCAL SEPARATION ---")
        print("Separating vocals from instrumental using HTDemucs...")
        separation_results = separator.separate(str(audio_file))
        
        vocal_path = separation_results['vocals']
        instrumental_path = separation_results['instrumental']
        
        print(f"✓ Vocals extracted: {vocal_path}")
        print(f"✓ Instrumental created: {instrumental_path}")
        
        # Step 2: Forced Alignment
        print("\n--- STEP 2: FORCED ALIGNMENT + VITERBI ---")
        print("Running ASR transcription...")
        
        # Generate ASR alignment
        asr_alignment_path = aligner.run_asr(vocal_path)
        print(f"✓ ASR transcription complete: {asr_alignment_path}")
        
        print("Running Viterbi alignment with lyrics...")
        # Align ASR to lyrics using Viterbi
        final_alignment_path = aligner.align_to_lyrics(asr_alignment_path, str(lyrics_file))
        print(f"✓ Viterbi alignment complete: {final_alignment_path}")
        
        # Step 3: Video Generation
        print("\n--- STEP 3: KARAOKE VIDEO GENERATION ---")
        print("Generating karaoke video with synchronized lyrics...")
        
        video_path = video_gen.generate(instrumental_path, final_alignment_path, base_name)
        print(f"✓ Karaoke video generated: {video_path}")
        
        # Summary
        print("\n=== PROCESS COMPLETE ===")
        results = {
            'original_audio': str(audio_file),
            'lyrics': str(lyrics_file),
            'vocals': vocal_path,
            'instrumental': instrumental_path,
            'asr_alignment': asr_alignment_path,
            'final_alignment': final_alignment_path,
            'karaoke_video': video_path,
            'base_name': base_name
        }
        
        print("Generated files:")
        for key, path in results.items():
            if key not in ['original_audio', 'lyrics', 'base_name']:
                print(f"  {key}: {path}")
        
        return results
        
    except Exception as e:
        print(f"Error during processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

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

def run_separation_only(input_dir, output_dir):
    """Run only the vocal separation step"""
    audio_file, _ = find_input_files(input_dir)
    if not audio_file:
        print("Error: Could not find audio file in input directory")
        return
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    separator = AudioSeparator(str(output_path))
    
    print(f"Separating audio: {audio_file.name}")
    results = separator.separate(str(audio_file))
    
    print("Separation complete!")
    for track, path in results.items():
        print(f"  {track}: {path}")


def main():
    parser = argparse.ArgumentParser(description='Generate karaoke video from audio and lyrics')
    parser.add_argument('--input_dir', help='Directory containing audio and lyrics files (not required for effects mode)')
    parser.add_argument('--output_dir', required=True, help='Directory for output files')
    parser.add_argument('--song_name', help='Custom name for output files (defaults to audio filename)')
    parser.add_argument('--mode', choices=['full', 'test', 'separation', 'effects'], default='full',
                       help='Processing mode: full (complete process), test (alignment only), separation (audio separation only), effects (karaoke effects test)')
    parser.add_argument('--text', default='GeeksforGeeks', help='Text for karaoke effects testing')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    
    # Check input_dir requirement for non-effects modes
    if args.mode != 'effects' and not args.input_dir:
        parser.error(f"--input_dir is required for mode '{args.mode}'")
    
    if args.mode == 'full':
        run_full_karaoke_process(args.input_dir, args.output_dir, args.song_name)
    elif args.mode == 'test':
        run_test_mode(args.input_dir, args.output_dir)
    elif args.mode == 'separation':
        run_separation_only(args.input_dir, args.output_dir)

if __name__ == "__main__":
    main() 