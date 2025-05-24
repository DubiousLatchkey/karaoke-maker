from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, AudioFileClip, concatenate_videoclips
import os
import json
from pathlib import Path

class KaraokeVideoGenerator:
    def __init__(self, output_dir, resolution="1280x720"):
        self.output_dir = output_dir
        
        # Parse resolution and ensure 16:9 aspect ratio
        if isinstance(resolution, str):
            if 'x' in resolution:
                width, height = map(int, resolution.split('x'))
            else:
                # If just height given, calculate 16:9 width
                height = int(resolution)
                width = int(height * 16 / 9)
        else:
            # Assume it's height as integer
            height = int(resolution)
            width = int(height * 16 / 9)
        
        # Ensure 16:9 aspect ratio
        if width / height != 16 / 9:
            # Adjust to closest 16:9
            if width / height > 16 / 9:
                width = int(height * 16 / 9)
            else:
                height = int(width * 9 / 16)
        
        self.resolution = (width, height)
        print(f"Video resolution set to: {width}x{height}")
        
        # Base resolution for scaling (1280x720)
        self.base_resolution = (1280, 720)
        self.scale_factor = height / 720  # Scale based on height
        
        # Scaled dimensions
        self.font_size = int(50 * self.scale_factor)
        self.text_width = int(1100 * self.scale_factor)
        self.stroke_width = max(1, int(1 * self.scale_factor))
        self.y_top = int(200 * self.scale_factor)
        self.y_bottom = int(520 * self.scale_factor)
        
        print(f"Scaling factor: {self.scale_factor:.2f}")
        print(f"Font size: {self.font_size}, Text width: {self.text_width}")
        print(f"Y positions: top={self.y_top}, bottom={self.y_bottom}")
        
    def generate(self, instrumental_path, alignment_path, output_name):
        """
        Generate karaoke video with timed lyrics in karaoke style
        
        Args:
            instrumental_path (str): Path to the instrumental audio
            alignment_path (str): Path to the alignment JSON file with line_end markers
            output_name (str): Name for the output video file
            
        Returns:
            str: Path to the generated video file
        """
        print(f"Loading alignment data from: {alignment_path}")
        
        # Load alignment data
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        print(f"Loaded {len(alignment_data)} word alignments")
        
        # Load audio
        print(f"Loading audio from: {instrumental_path}")
        audio = AudioFileClip(instrumental_path)
        duration = audio.duration
        print(f"Audio duration: {duration:.2f} seconds")
        
        # Group words into lines based on line_end markers
        lines = self._group_words_into_lines(alignment_data)
        print(f"Grouped into {len(lines)} karaoke lines")
        
        # Create background with scaled resolution
        background = ColorClip(size=self.resolution, color=(0, 0, 0), duration=duration)
        
        # Create karaoke line clips
        line_clips = []
        for i, line in enumerate(lines):
            is_top = (i % 2 == 0)  # Alternate between top and bottom
            line_clip = self._create_karaoke_line_clip(line, is_top, duration)
            if line_clip:
                # Position the clip based on whether it should be top or bottom
                y_position = self.y_top if is_top else self.y_bottom
                positioned_clip = line_clip.set_position(('center', y_position))
                line_clips.append(positioned_clip)
                print(f"  Positioned line {i+1} at y={y_position}")
        
        print(f"Created {len(line_clips)} positioned line clips")
        
        # Combine all clips
        print("Compositing video...")
        final_video = CompositeVideoClip([background] + line_clips)
        
        # Add audio
        final_video = final_video.set_audio(audio)
        
        # Write output file
        output_path = os.path.join(self.output_dir, f"{output_name}.mp4")
        print(f"Writing video to: {output_path}")
        
        final_video.save_frame("frame.png", t=26)

        final_video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            verbose=False,
            logger="bar"
        )
        

        # Clean up
        audio.close()
        final_video.close()
        
        print(f"Karaoke video generation complete!")
        return output_path
    
    def _group_words_into_lines(self, alignment_data):
        """
        Group words into lines based on line_end markers
        
        Args:
            alignment_data: List of word alignment dictionaries
            
        Returns:
            List of line dictionaries, each containing words and timing info
        """
        lines = []
        current_line = []
        
        for word in alignment_data:
            # Skip words without valid timing
            if word.get('begin') is None or word.get('end') is None:
                continue
                
            current_line.append(word)
            
            # If this word marks the end of a line, complete the line
            if word.get('line_end', False):
                if current_line:
                    line_start = min(w['begin'] for w in current_line)
                    line_end = max(w['end'] for w in current_line)
                    line_text = ' '.join(w['text'] for w in current_line)
                    
                    lines.append({
                        'words': current_line.copy(),
                        'text': line_text,
                        'start': line_start,
                        'end': line_end,
                        'line_number': len(lines)
                    })
                    print(f"Line {len(lines)}: '{line_text}' ({line_start:.2f}s - {line_end:.2f}s)")
                    current_line = []
        
        # Handle any remaining words (in case last line doesn't have line_end marker)
        if current_line:
            line_start = min(w['begin'] for w in current_line)
            line_end = max(w['end'] for w in current_line)
            line_text = ' '.join(w['text'] for w in current_line)
            
            lines.append({
                'words': current_line.copy(),
                'text': line_text,
                'start': line_start,
                'end': line_end,
                'line_number': len(lines)
            })
            print(f"Line {len(lines)}: '{line_text}' ({line_start:.2f}s - {line_end:.2f}s)")
        
        return lines
    
    def _preprocess_line_text(self, line_text, max_chars_per_line=40):
        """
        Preprocess line text to add newlines at appropriate places for better display
        
        Args:
            line_text: Original line text
            max_chars_per_line: Maximum characters per line before breaking
            
        Returns:
            Text with newlines inserted at good break points
        """
        words = line_text.split()
        if not words:
            return line_text
            
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            # Check if adding this word would exceed the line limit
            word_length = len(word)
            space_length = 1 if current_line else 0  # Space before word (except first word)
            
            if current_length + space_length + word_length <= max_chars_per_line:
                # Word fits on current line
                current_line.append(word)
                current_length += space_length + word_length
            else:
                # Word doesn't fit, start new line
                if current_line:  # Only add line if it has content
                    lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length
        
        # Add the last line if it has content
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)
    
    def _create_mask_text_with_newlines(self, preprocessed_full_text, revealed_words):
        """
        Create mask text that maintains newline structure while revealing only certain words
        
        Args:
            preprocessed_full_text: Full text with newlines already inserted
            revealed_words: List of words that should be revealed
            
        Returns:
            Mask text with revealed words and spaces for unrevealed parts, maintaining newlines
        """
        if not revealed_words:
            # Return text with all words replaced by spaces, maintaining structure
            result = ""
            for char in preprocessed_full_text:
                if char == '\n':
                    result += '\n'
                else:
                    result += ' '
            return result
        
        # Create the revealed text string
        revealed_text = ' '.join(revealed_words)
        
        # Split both texts into words while preserving position information
        full_words = []
        current_word = ""
        word_positions = []  # (start_pos, end_pos, word)
        pos = 0
        
        # Parse the full text to get word positions
        for i, char in enumerate(preprocessed_full_text):
            if char.isspace() or char == '\n':
                if current_word:
                    word_positions.append((pos, pos + len(current_word), current_word.upper()))
                    current_word = ""
                    pos = i + 1
                elif char == '\n':
                    # Keep track of newlines
                    pass
            else:
                current_word += char
        
        # Don't forget the last word if text doesn't end with space
        if current_word:
            word_positions.append((pos, pos + len(current_word), current_word.upper()))
        
        # Create mask by revealing words progressively
        mask_chars = list(preprocessed_full_text)
        revealed_word_count = 0
        
        for start_pos, end_pos, word in word_positions:
            if revealed_word_count < len(revealed_words):
                # This word should be revealed
                revealed_word_count += 1
            else:
                # This word should be hidden (replaced with spaces)
                for i in range(len(word)):
                    if start_pos + i < len(mask_chars):
                        mask_chars[start_pos + i] = ' '
        
        return ''.join(mask_chars)

    def _create_karaoke_line_clip(self, line, is_top, total_duration):
        """
        Create a karaoke line clip with progressive word highlighting using individual masked clips
        
        Args:
            line: Line dictionary with words and timing
            is_top: Boolean indicating if line should be in top half
            total_duration: Total video duration
            
        Returns:
            VideoClip for this line with karaoke highlighting effect
        """
        try:
            print(f"Creating karaoke line clip: '{line['text'][:50]}...'")
            print(f"  Line timing: {line['start']:.2f}s - {line['end']:.2f}s")
            print(f"  Words: {len(line['words'])}")
            
            # Preprocess the line text with newlines
            line_text = line['text'].upper()
            preprocessed_text = self._preprocess_line_text(line_text)
            print(f"  Preprocessed text:\n{repr(preprocessed_text)}")
            
            # Set timing for the line
            start_time = max(0, line['start'] - 0.5)
            end_time = line['end'] + 0.5
            duration = end_time - start_time
        
            # Start with the base white clip
            clips = []
            
            # Create progressive yellow clips for each word
            words_so_far = []
            
            for i, word in enumerate(line['words']):
                # Skip words without valid timing
                if word.get('begin') is None or word.get('end') is None:
                    continue
                
                # Add this word to the list of revealed words
                words_so_far.append(word['text'].upper())
                
                # Calculate timing for this word
                word_start = max(start_time, float(word['begin']))
                word_duration = end_time - word_start
                
                if word_duration <= 0:
                    continue
                
                # Create yellow text of the whole preprocessed line
                yellow_text = TextClip(
                    preprocessed_text,
                    fontsize=self.font_size,
                    color='yellow',
                    font='DejaVu-Sans-Mono',
                    stroke_color='black',
                    stroke_width=self.stroke_width
                ).set_start(word_start).set_duration(word_duration)
                
                # Create mask text with proper newline handling
                mask_text = self._create_mask_text_with_newlines(preprocessed_text, words_so_far)
                
                word_mask = TextClip(
                    mask_text,
                    fontsize=self.font_size,
                    color='white',  # White reveals, black hides
                    font='DejaVu-Sans-Mono',
                    bg_color='black'
                ).set_start(word_start).set_duration(word_duration)
                
                # Convert to mask
                word_mask = word_mask.to_mask()
                
                # Apply mask to yellow text
                masked_yellow = yellow_text.set_mask(word_mask)
                
                # Add to clips list
                clips.append(masked_yellow)
            
            # Create base white text of the whole preprocessed line (always visible)
            base_white = TextClip(
                preprocessed_text,
                fontsize=self.font_size,
                color='white',
                font='DejaVu-Sans-Mono',
                stroke_color='black',
                stroke_width=self.stroke_width
            ).set_start(start_time).set_duration(duration).fadein(0.5).fadeout(0.5)

            # If no valid word clips were created, return just the white text
            if len(clips) == 0:
                print("  No valid word clips created, using simple white display")
                return base_white
            
            # Combine all clips into one composite clip
            final_clip = CompositeVideoClip([base_white] + clips)
            
            print(f"  Created karaoke clip with {len(clips)} progressive yellow clips")
            
            return final_clip
            
        except Exception as e:
            print(f"Error creating karaoke line clip for '{line['text']}': {e}")
            import traceback
            traceback.print_exc()
            return None
    
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
        
        # Create black background with scaled resolution
        background = ColorClip(size=self.resolution, color=(0, 0, 0), duration=duration)
        
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
                
                # Create text clip for this word with scaled font size
                text_clip = (TextClip(
                    word['text'].upper(),  # Convert to uppercase for better visibility
                    fontsize=int(60 * self.scale_factor),  # Scale test mode font size
                    color='white',
                    font='DejaVu-Sans-Mono',  # Changed to monospaced font
                    stroke_color='black',
                    stroke_width=self.stroke_width
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
    
    parser = argparse.ArgumentParser(description='Generate karaoke video from alignment data')
    parser.add_argument('--audio', required=True, help='Path to audio file (instrumental or full song)')
    parser.add_argument('--alignment', required=True, help='Path to lyrics alignment JSON file from Viterbi')
    parser.add_argument('--output_dir', help='Directory for output files (defaults to alignment file directory)')
    parser.add_argument('--output_name', help='Name for output video file (defaults to alignment filename)')
    parser.add_argument('--resolution', default='1280x720', 
                        help='Video resolution. Options: "WIDTHxHEIGHT" (e.g. "1920x1080") or just "HEIGHT" (e.g. "1080" for 1920x1080). Always maintains 16:9 aspect ratio (default: 1280x720)')
    parser.add_argument('--mode', choices=['test', 'karaoke'], default='karaoke',
                        help='Generation mode: "test" for simple word-by-word, "karaoke" for full karaoke style (default: karaoke)')
    args = parser.parse_args()
    
    # Set default output directory to alignment file's directory
    if args.output_dir is None:
        args.output_dir = str(Path(args.alignment).parent)
    
    # Set default output name to alignment filename
    if args.output_name is None:
        args.output_name = Path(args.alignment).stem
        
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize video generator with specified resolution
    video_gen = KaraokeVideoGenerator(args.output_dir, resolution=args.resolution)
    
    print(f"Generating {args.mode} video...")
    print(f"Audio: {args.audio}")
    print(f"Alignment: {args.alignment}")
    print(f"Resolution: {args.resolution} -> {video_gen.resolution[0]}x{video_gen.resolution[1]}")
    print(f"Output directory: {args.output_dir}")
    print(f"Output name: {args.output_name}")
    print("-" * 50)
    
    try:
        if args.mode == 'test':
            # Generate simple test video
            video_path = video_gen.test_alignment(args.audio, args.alignment, args.output_name)
        else:  # karaoke mode
            # Generate full karaoke video
            video_path = video_gen.generate(args.audio, args.alignment, args.output_name)
            
        print(f"\n✓ {args.mode.capitalize()} video generated successfully: {video_path}")
        print(f"\nWorkflow summary:")
        print(f"1. ASR: python forced_alignment.py --mode asr --input song.mp3")
        print(f"2. Viterbi: python forced_alignment.py --mode viterbi --input song_alignment.json --lyrics lyrics.txt")
        print(f"3. Video: python video_generator.py --audio instrumental.mp3 --alignment song_lyrics_alignment.json --mode karaoke --resolution 1080")
    except Exception as e:
        print(f"✗ Error generating video: {e}")
        import traceback
        traceback.print_exc() 