from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, AudioFileClip
import os
import json

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
            alignment_path (str): Path to the alignment JSON file
            output_name (str): Name for the output video file
            
        Returns:
            str: Path to the generated test video
        """
        # Load alignment data
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        # Load audio
        audio = AudioFileClip(audio_path)
        duration = audio.duration
        
        # Create black background
        background = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=duration)
        
        # Create text clips for each word
        text_clips = []
        for word in alignment_data:
            # Create text clip for this word
            text_clip = (TextClip(
                word['text'],
                fontsize=100,
                color='white',
                font='Arial-Bold',
                stroke_color='black',
                stroke_width=2
            )
            .set_start(word['begin'])
            .set_end(word['end'])
            .set_position(('center', 'center')))
            
            text_clips.append(text_clip)
        
        # Combine all clips
        final_video = CompositeVideoClip([background] + text_clips)
        
        # Add audio
        final_video = final_video.set_audio(audio)
        
        # Write output file
        output_path = os.path.join(self.output_dir, f"{output_name}_test.mp4")
        final_video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac'
        )
        
        return output_path

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test video generation')
    parser.add_argument('--audio', required=True, help='Path to audio file')
    parser.add_argument('--alignment', required=True, help='Path to alignment JSON file')
    parser.add_argument('--output_dir', required=True, help='Directory for output files')
    parser.add_argument('--output_name', required=True, help='Name for output video file (without extension)')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize video generator
    video_gen = KaraokeVideoGenerator(args.output_dir)
    
    # Generate test video
    print(f"Generating test video...")
    video_path = video_gen.test_alignment(args.audio, args.alignment, args.output_name)
    
    print(f"Test video generated successfully: {video_path}") 