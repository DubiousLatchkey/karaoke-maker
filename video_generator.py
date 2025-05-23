from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, AudioFileClip
import os
import json
from pathlib import Path

class KaraokeVideoGenerator:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        
    def generate(self, instrumental_path, alignment_data, output_name):
        """
        Generate karaoke video with timed lyrics
        
        Args:
            instrumental_path (str): Path to the instrumental audio
            alignment_data (list): List of dictionaries containing timing and text
            output_name (str): Name for the output video file
            
        Returns:
            str: Path to the generated video file
        """
        # TODO: Implement video generation
        # 1. Create background
        # 2. Create text clips for each line
        # 3. Combine clips
        # 4. Add audio
        # 5. Write output file
        pass

    def test_alignment(self, audio_path, alignment_path, output_name):
        """
        Test function to create a simple word-by-word karaoke display.
        This helps verify that the alignment is working correctly.
        
        Args:
            audio_path (str): Path to the audio file (can be full song or vocals)
            alignment_path (str): Path to the alignment JSON file from Viterbi alignment
            output_name (str): Name for the output video file
            
        Returns:
            str: Path to the generated test video
        """
        print(f"Loading alignment data from: {alignment_path}")
        
        # Load alignment data
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        print(f"Loaded {len(alignment_data)} word alignments")
        
        # Filter out words without timing information
        valid_words = []
        skipped_words = []
        
        for word in alignment_data:
            if word.get('begin') is not None and word.get('end') is not None:
                valid_words.append(word)
            else:
                skipped_words.append(word.get('text', 'unknown'))
        
        print(f"Valid words with timing: {len(valid_words)}")
        if skipped_words:
            print(f"Skipped words without timing: {skipped_words[:10]}{'...' if len(skipped_words) > 10 else ''}")
        
        # Load audio
        print(f"Loading audio from: {audio_path}")
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        print(f"Audio duration: {duration:.2f} seconds")
        
        # Create black background
        background = ColorClip(size=(1280, 720), color=(0, 0, 0), duration=duration)
        
        # Create text clips for each word with valid timing
        text_clips = []
        for i, word in enumerate(valid_words):
            try:
                # Get timing information
                start_time = float(word['begin'])
                end_time = float(word['end'])
                
                # Fix timing if start > end by swapping them
                if start_time > end_time:
                    print(f"Swapping times for word '{word['text']}': {start_time:.2f} - {end_time:.2f} -> {end_time:.2f} - {start_time:.2f}")
                    start_time, end_time = end_time, start_time
                
                # Skip words with invalid timing (after potential swap)
                if start_time >= end_time or start_time < 0 or end_time > duration:
                    print(f"Skipping word '{word['text']}' with invalid timing: {start_time:.2f} - {end_time:.2f}")
                    continue
                
                # Create text clip for this word
                text_clip = (TextClip(
                    word['text'].upper(),  # Convert to uppercase for better visibility
                    fontsize=80,  # Scaled down for 720p (was 120 for 1080p)
                    color='white',
                    font='Arial-Bold',
                    stroke_color='black',
                    stroke_width=2  # Also scaled down stroke width
                )
                .set_start(start_time)
                .set_end(end_time)
                .set_position(('center', 'center')))
                
                text_clips.append(text_clip)
                
                # Show progress every 50 words
                if (i + 1) % 50 == 0:
                    print(f"Processed {i + 1}/{len(valid_words)} words...")
                    
            except Exception as e:
                print(f"Error processing word {word.get('text', 'unknown')}: {e}")
                continue
        
        print(f"Created {len(text_clips)} text clips")
        
        # Combine all clips
        print("Compositing video...")
        final_video = CompositeVideoClip([background] + text_clips)
        
        # Add audio
        final_video = final_video.set_audio(audio)
        
        # Write output file
        output_path = os.path.join(self.output_dir, f"{output_name}_test.mp4")
        print(f"Writing video to: {output_path}")
        
        final_video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            verbose=False,
            logger=None
        )
        
        # Clean up
        audio.close()
        final_video.close()
        
        print(f"Video generation complete!")
        return output_path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate test karaoke video from alignment data')
    parser.add_argument('--audio', required=True, help='Path to audio file (instrumental or full song)')
    parser.add_argument('--alignment', required=True, help='Path to lyrics alignment JSON file from Viterbi')
    parser.add_argument('--output_dir', help='Directory for output files (defaults to alignment file directory)')
    parser.add_argument('--output_name', help='Name for output video file (defaults to alignment filename)')
    args = parser.parse_args()
    
    # Set default output directory to alignment file's directory
    if args.output_dir is None:
        args.output_dir = str(Path(args.alignment).parent)
    
    # Set default output name to alignment filename
    if args.output_name is None:
        args.output_name = Path(args.alignment).stem
        
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize video generator
    video_gen = KaraokeVideoGenerator(args.output_dir)
    
    print(f"Generating test karaoke video...")
    print(f"Audio: {args.audio}")
    print(f"Alignment: {args.alignment}")
    print(f"Output directory: {args.output_dir}")
    print(f"Output name: {args.output_name}")
    print("-" * 50)
    
    try:
        # Generate test video
        video_path = video_gen.test_alignment(args.audio, args.alignment, args.output_name)
        print(f"\n✓ Test video generated successfully: {video_path}")
        print(f"\nUsage examples:")
        print(f"1. First run ASR: python forced_alignment.py --mode asr --input song.mp3")
        print(f"2. Then run Viterbi: python forced_alignment.py --mode viterbi --input song_alignment.json --lyrics lyrics.txt")
        print(f"3. Finally test video: python video_generator.py --audio instrumental.mp3 --alignment song_lyrics_alignment.json")
    except Exception as e:
        print(f"✗ Error generating video: {e}")
        import traceback
        traceback.print_exc() 