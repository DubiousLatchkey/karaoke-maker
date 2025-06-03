import os
import json
from pathlib import Path
import numpy as np
import dotenv
import aubio
dotenv.load_dotenv(dotenv_path='.env')

# Load font configurations from environment variables
FONT_NAME = os.getenv('FONT_NAME', 'Cascadia-Mono-Regular')
FONT_COLOR_ACTIVE = os.getenv('FONT_COLOR_ACTIVE', 'yellow')
FONT_COLOR_INACTIVE = os.getenv('FONT_COLOR_INACTIVE', 'white')
FONT_KERNING = int(os.getenv('FONT_KERNING', '1'))

image_magick_path = os.getenv('IMAGEMAGICK_BINARY', None)
print(f"ImageMagick path: {image_magick_path}")
print(f"Font configuration: {FONT_NAME}, kerning={FONT_KERNING}")
print(f"Colors: active={FONT_COLOR_ACTIVE}, inactive={FONT_COLOR_INACTIVE}")

from moviepy.config import change_settings
from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, AudioFileClip, VideoClip, concatenate_videoclips

if image_magick_path:
    print(f"Setting ImageMagick path to: {image_magick_path}")
    change_settings({"IMAGEMAGICK_BINARY": image_magick_path})



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
        
    def generate(self, instrumental_path, alignment_path, output_name, use_wipe=True, song_title="", artist=""):
        """
        Generate karaoke video with timed lyrics in karaoke style
        
        Args:
            instrumental_path (str): Path to the instrumental audio
            alignment_path (str): Path to the alignment JSON file with line_end markers
            output_name (str): Name for the output video file
            use_wipe (bool): Whether to use wipe transitions instead of progressive highlighting
            song_title (str): Title of the song (for intro)
            artist (str): Artist of the song (for intro)
            
        Returns:
            str: Path to the generated video file
        """
        print(f"Loading alignment data from: {alignment_path}")
        
        # Load alignment data
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        print(f"Loaded {len(alignment_data)} word alignments")
        
        # Load audio and detect BPM
        print(f"Loading audio from: {instrumental_path}")
        audio = AudioFileClip(instrumental_path)
        duration = audio.duration
        print(f"Audio duration: {duration:.2f} seconds")
        
        # Detect BPM and beats using aubio
        print("Detecting beats...")
        src = aubio.source(instrumental_path, hop_size=256)
        tempo = aubio.tempo('default', 512, 256, src.samplerate)
        beat_times = []
        current_frame = 0
        
        while True:
            samples, read = src()
            if read == 0:
                break
                
            is_beat = tempo(samples)
            if is_beat:
                beat_time = current_frame * 256 / src.samplerate
                beat_times.append(beat_time)
                
            current_frame += 1
            
        detected_tempo = tempo.get_bpm()
        print(f"Detected BPM: {detected_tempo:.1f}")
        print(f"Found {len(beat_times)} beats")
        
        # Group words into lines based on line_end markers
        lines = self._group_words_into_lines(alignment_data)
        print(f"Grouped into {len(lines)} karaoke lines")
        
        # Create background with scaled resolution
        background = ColorClip(size=self.resolution, color=(0, 0, 0), duration=duration)
        
        # Create karaoke line clips
        line_clips = []
        
        # Process each line and detect gaps
        for i, line in enumerate(lines):
            is_top = (i % 2 == 0)  # Alternate between top and bottom
            
            # Choose which line clip function to use based on use_wipe parameter
            if use_wipe:
                line_clip = self._create_karaoke_line_clip_wipe(line, is_top, duration)
                clip_type = "wipe"
            else:
                line_clip = self._create_karaoke_line_clip(line, is_top, duration)
                clip_type = "karaoke"
                
            if line_clip:
                # Position the clip based on whether it should be top or bottom
                y_position = self.y_top if is_top else self.y_bottom
                positioned_clip = line_clip.set_position(('center', y_position))
                line_clips.append(positioned_clip)
                print(f"  Positioned {clip_type} line {i+1} at y={y_position}")
            
            # Check for gap between this line and the next
            if i < len(lines) - 1:
                gap_duration = lines[i + 1]['start'] - line['end']
                if gap_duration > 10:
                    break_text = f"[{int(gap_duration)} second break]"
                    break_clip = TextClip(
                        break_text,
                        fontsize=self.font_size,
                        color=FONT_COLOR_INACTIVE,
                        font=FONT_NAME,
                        kerning=FONT_KERNING,
                        stroke_color=FONT_COLOR_INACTIVE,
                        stroke_width=self.stroke_width
                    ).set_start(line['end'] + 1).set_duration(gap_duration - 2).set_position(('center', 'center'))
                    break_clip = break_clip.fadein(1).fadeout(1)
                    line_clips.append(break_clip)
                    print(f"Added break message: {break_text}")
                    
                    # Add count-in dots if gap is long enough for count-in
                    if gap_duration > 10:  # Changed from 3 * beat_duration since we'll use actual beats
                        # Find the last 8 beats before the next section starts
                        next_section_start = lines[i + 1]['start']
                        # Filter out beats that are too close to the next section start
                        BEAT_THRESHOLD = 0.075  # Ignore beats within 75ms of section start
                        count_in_beats = [t for t in beat_times if t < next_section_start - BEAT_THRESHOLD][-8:]
                        
                        if len(count_in_beats) >= 8:
                            count_in_y = self.y_top - int(80 * self.scale_factor)  # Position above the top line
                            
                            # Create dots that appear on beats 8, 6, and 4, each lasting 2 beats
                            for i, dot_count in enumerate([8, 6, 4]):
                                beat_time = count_in_beats[-dot_count]
                                dots = "*" * ((dot_count // 2 - 1))  # 4, 3, 2 stars
                                
                                # Each set of dots lasts for 2 beats
                                next_dot_time = count_in_beats[-(dot_count-2)]  # Time of next set
                                duration = next_dot_time - beat_time
                                
                                dot_clip = TextClip(
                                    dots,
                                    fontsize=self.font_size,
                                    color=FONT_COLOR_INACTIVE,
                                    font=FONT_NAME,
                                    kerning=FONT_KERNING,
                                    stroke_color=FONT_COLOR_INACTIVE,
                                    stroke_width=self.stroke_width
                                ).set_start(beat_time).set_duration(duration).set_position(('center', count_in_y))
                                line_clips.append(dot_clip)
                                print(f"Added count-in dot {dot_count//2} at {beat_time:.2f}s (duration: {duration:.2f}s)")
        
        print(f"Created {len(line_clips)} positioned line clips")

        # Handle outro if there's a significant gap after the last line
        if lines:
            last_line_end = lines[-1]['end']
            outro_duration = duration - last_line_end
            if outro_duration > 10:
                outro_text = f"[{int(outro_duration)} second outro]"
                outro_clip = TextClip(
                    outro_text,
                    fontsize=self.font_size,
                    color=FONT_COLOR_INACTIVE,
                    font=FONT_NAME,
                    kerning=FONT_KERNING,
                    stroke_color=FONT_COLOR_INACTIVE,
                    stroke_width=self.stroke_width
                ).set_start(last_line_end + 2).set_duration(outro_duration - 2).set_position(('center', 'center'))
                outro_clip = outro_clip.fadein(1).fadeout(1)
                line_clips.append(outro_clip)
                print(f"Added outro message: {outro_text}")

        # Handle intro based on timing of first line
        first_line_start = lines[0]['start'] if lines else 0
        intro_clips = []

        # Process song title and artist to add newlines if needed
        if len(song_title) > 35:
            # Split on space closest to 35 chars
            split_index = song_title.rfind(' ', 0, 35)
            if split_index != -1:
                song_title = song_title[:split_index] + '\n' + song_title[split_index+1:]
        
        if artist and len(artist) > 35:
            # Split on space closest to 35 chars
            split_index = artist.rfind(' ', 0, 35)
            if split_index != -1:
                artist = artist[:split_index] + '\n' + artist[split_index+1:]
        
        if first_line_start >= 5:
            # Create intro clip to be composited with the main video
            intro_text = f"{song_title}\n{artist}" if artist else song_title
            intro_clip = TextClip(
                intro_text,
                fontsize=self.font_size,
                color=FONT_COLOR_INACTIVE,
                font=FONT_NAME,
                kerning=FONT_KERNING,
                stroke_color=FONT_COLOR_INACTIVE,
                stroke_width=self.stroke_width,
                align='center'
            ).set_duration(first_line_start - 1).set_position(('center', 'center'))
            intro_clip = intro_clip.fadein(1).fadeout(1)
            line_clips.append(intro_clip)
        else:
            print(f"Added intro title during musical intro")
            # Create separate 5-second intro clip
            intro_text = f"{song_title}\n{artist}" if artist else song_title
            intro_clip = TextClip(
                intro_text,
                fontsize=self.font_size,
                color=FONT_COLOR_INACTIVE,
                font=FONT_NAME,
                kerning=FONT_KERNING,
                stroke_color=FONT_COLOR_INACTIVE,
                stroke_width=self.stroke_width,
                align='center'
            ).set_duration(5).set_position(('center', 'center'))
            intro_clip = intro_clip.fadein(1).fadeout(1)
            intro_clips.append(intro_clip)
            print(f"Created separate 5-second intro clip")
        
        # Combine all clips
        mode_name = "wipe" if use_wipe else "karaoke"
        print(f"Compositing {mode_name} video...")
        final_video = CompositeVideoClip([background] + line_clips, use_bgclip=True)

        if intro_clips:
            intro_video = CompositeVideoClip([ColorClip(size=self.resolution, color=(0, 0, 0), duration=5)] + intro_clips)
            final_video = concatenate_videoclips([intro_video, final_video])
        
        
        # Add audio
        final_video = final_video.set_audio(audio)
        
        # Sanitize output filename
        sanitized_name = "".join(c for c in output_name if c.isalnum() or c in (' ', '-', '_')).strip()
        sanitized_name = sanitized_name.replace(' ', '_')
        
        # Write output file
        output_path = os.path.join(self.output_dir, f"{sanitized_name}.mp4")
        print(f"Writing {mode_name} video to: {output_path}")
        
        final_video.write_videofile(
            output_path,
            fps=24,
            codec='libx264',
            audio_codec='aac',
            verbose=False,
            logger="bar",
            threads=4,
            preset="ultrafast"
        )
        
        # Clean up
        audio.close()
        final_video.close()
        
        print(f"Karaoke {mode_name} video generation complete!")
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

    def _create_word_spacing_for_wipe(self, preprocessed_text, target_word, word_index=0):
        """
        Create padded text with spaces where only the target word is revealed
        
        Args:
            preprocessed_text: Full text with newlines already inserted
            target_word: The word that should be revealed (others replaced with spaces)
            word_index: Which occurrence of target_word to reveal (0-based index)
            
        Returns:
            Text with only target word visible and other words replaced by spaces, maintaining newlines
        """
        word_spacing = ' ' * len(preprocessed_text)  # Start with all spaces
        # Find the word position and replace just that word
        current_word = ""
        word_positions = []  # (start_pos, end_pos, word)
        pos = 0
        
        # Parse the text to get word positions
        for i, char in enumerate(preprocessed_text):
            if char.isspace() or char == '\n':
                if current_word:
                    word_positions.append((pos, pos + len(current_word), current_word.upper()))
                    current_word = ""
                    pos = i + 1
                if char == '\n':
                    # Preserve newlines in the spacing
                    word_spacing = word_spacing[:i] + '\n' + word_spacing[i+1:]
            else:
                current_word += char
        
        # Handle last word
        if current_word:
            word_positions.append((pos, pos + len(current_word), current_word.upper()))
        
        # Find all occurrences of the target word and replace only the specified one
        target_occurrences = []
        for start_pos, end_pos, word in word_positions:
            if word == target_word:
                target_occurrences.append((start_pos, end_pos, word))
        
        # Replace the target word occurrence at the specified index
        if word_index < len(target_occurrences):
            start_pos, end_pos, word = target_occurrences[word_index]
            word_spacing = word_spacing[:start_pos] + target_word + word_spacing[end_pos:]
        else:
            # If word_index is out of range, fall back to first occurrence
            if target_occurrences:
                start_pos, end_pos, word = target_occurrences[0]
                word_spacing = word_spacing[:start_pos] + target_word + word_spacing[end_pos:]

        
        return word_spacing

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
            start_time = max(0, line['start'] - 0.6)
            end_time = line['end'] + 0.4
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
                    color=FONT_COLOR_ACTIVE,
                    font=FONT_NAME,
                    kerning=FONT_KERNING,
                    stroke_color=FONT_COLOR_ACTIVE,
                    stroke_width=self.stroke_width
                ).set_start(word_start).set_duration(word_duration)
                
                # Create mask text with proper newline handling
                mask_text = self._create_mask_text_with_newlines(preprocessed_text, words_so_far)
                
                word_mask = TextClip(
                    mask_text,
                    fontsize=self.font_size,
                    color=FONT_COLOR_INACTIVE,  # White reveals, black hides
                    font=FONT_NAME,
                    kerning=FONT_KERNING,
                    bg_color='black',
                    stroke_color=FONT_COLOR_INACTIVE,
                    stroke_width=self.stroke_width
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
                color=FONT_COLOR_INACTIVE,
                font=FONT_NAME,
                kerning=FONT_KERNING,
                stroke_color=FONT_COLOR_INACTIVE,
                stroke_width=self.stroke_width
            ).set_start(start_time).set_duration(duration).fadein(0.3).fadeout(0.4)

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
    
    def _create_karaoke_line_clip_wipe(self, line, is_top, total_duration):
        """
        Create a karaoke line clip with wipe transition effects for each word
        
        Args:
            line: Line dictionary with words and timing
            is_top: Boolean indicating if line should be in top half
            total_duration: Total video duration
            
        Returns:
            VideoClip for this line with karaoke wipe highlighting effect
        """
        try:
            print(f"Creating karaoke line clip (wipe): '{line['text'][:50]}...'")
            print(f"  Line timing: {line['start']:.2f}s - {line['end']:.2f}s")
            print(f"  Words: {len(line['words'])}")
            
            # Preprocess the line text with newlines
            line_text = line['text'].upper()
            preprocessed_text = self._preprocess_line_text(line_text)
            print(f"  Preprocessed text:\n{repr(preprocessed_text)}")
            
            # Set timing for the line
            start_time = max(0, line['start'] - 0.6)
            end_time = line['end'] + 0.4
            duration = end_time - start_time
            
            # Filter out words without valid timing
            valid_words = []
            for word in line['words']:
                if word.get('begin') is not None and word.get('end') is not None:
                    valid_words.append(word)
            
            if not valid_words:
                print("  No valid words found, creating simple white text")
                return TextClip(
                    preprocessed_text,
                    fontsize=self.font_size,
                    color=FONT_COLOR_INACTIVE,
                    font=FONT_NAME,
                    kerning=FONT_KERNING,
                    stroke_color=FONT_COLOR_INACTIVE,
                    stroke_width=self.stroke_width
                ).set_start(start_time).set_duration(duration).fadein(0.3).fadeout(0.4)
            
            # Create base white text (always visible)
            base_white = TextClip(
                preprocessed_text,
                fontsize=self.font_size,
                color=FONT_COLOR_INACTIVE,
                font=FONT_NAME,
                kerning=FONT_KERNING,
                stroke_color=FONT_COLOR_INACTIVE,
                stroke_width=self.stroke_width
            ).set_start(start_time).set_duration(duration).fadein(0.3).fadeout(0.4).set_position(('center', 'center'))
            
            # Create yellow text for the complete line
            yellow_text = TextClip(
                preprocessed_text,
                fontsize=self.font_size,
                color=FONT_COLOR_ACTIVE,
                font=FONT_NAME,
                kerning=FONT_KERNING,
                stroke_color=FONT_COLOR_ACTIVE,
                stroke_width=self.stroke_width
            ).set_start(start_time).set_duration(duration).fadein(0.3).fadeout(0.4).set_position(('center', 'center'))
            
            print(f"  Creating wipe effects for {len(valid_words)} words...")
            
            # Create Wipe instances for each word
            word_wipes = []
            word_occurrence_count = {}  # Track how many times we've seen each word
            
            for word in valid_words:
                word_text = word['text'].upper()
                
                # Track which occurrence of this word we're processing
                if word_text not in word_occurrence_count:
                    word_occurrence_count[word_text] = 0
                else:
                    word_occurrence_count[word_text] += 1
                
                current_word_index = word_occurrence_count[word_text]
                
                # Create padded text where other words are replaced with spaces
                # Use the same logic as the existing mask function to handle newlines properly
                # Create padded text with spaces before and after this word
                word_spacing = self._create_word_spacing_for_wipe(preprocessed_text, word_text, current_word_index)
                
                #print(f"    Created spaced word string with length {len(word_spacing)}")
                
                # Create Wipe instance
                wipe = Wipe(word_text, word_spacing, self.resolution, self.font_size, self.stroke_width)
                word_wipes.append((wipe, word))
            
            # Create masked yellow clips for each word
            masked_clips = []
            for wipe, word in word_wipes:
                begin_time = float(word['begin'])
                end_time = float(word['end'])
                this_duration = end_time - begin_time
                
                # # Create mask clip for this word
                # def make_mask_frame(t, w=wipe, bt=begin_time, dur=this_duration):
                #     return w.create_wipe_mask(t, bt, dur)
                
                def make_mask_frame_local(t, w=wipe, dur=this_duration):
                    return w.create_wipe_mask_local(t, dur)
                
                mask_clip = VideoClip(make_mask_frame_local, duration=this_duration)
                final_mask = mask_clip.to_mask()
                
                # Apply mask to yellow text
                relative_start_time = begin_time - start_time
                masked_yellow = yellow_text.set_mask(final_mask).set_start(begin_time).set_duration(duration - relative_start_time).fadeout(0.4)
                masked_clips.append(masked_yellow)

                # Write masked yellow clip to file for debugging
                # single_clip = CompositeVideoClip([base_white, masked_yellow], size=self.resolution)
                # single_clip.fps = 24
                # single_clip.write_videofile(f"masked_yellow_{word['text']}.mp4", verbose=False, logger="bar")
                # single_clip.close()
                
                print(f"    Created wipe mask for '{word['text']}' ({begin_time:.2f}s - {end_time:.2f}s)")
            
            # Combine all clips
            all_clips = [base_white] + masked_clips
            final_clip = CompositeVideoClip(all_clips)
            
            print(f"  Created karaoke wipe clip with {len(masked_clips)} word wipes")
            
            return final_clip
            
        except Exception as e:
            print(f"Error creating karaoke wipe line clip for '{line['text']}': {e}")
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
                    color=FONT_COLOR_INACTIVE,
                    font=FONT_NAME,  # Changed to monospaced font
                    kerning=FONT_KERNING,
                    stroke_color=FONT_COLOR_INACTIVE,
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

class Wipe:
    """
    A class to handle wipe transition calculations for a single word.
    Analyzes boundaries from a padded single-frame text clip.
    """
    
    def __init__(self, word_text, word_spacing, screensize=(720, 460), font_size=None, stroke_width=1):
        """
        Initialize wipe transition for a word.
        
        Args:
            word_text: The word to analyze
            word_spacing: Full text with proper spacing (padded with spaces)
            screensize: Video dimensions
            font_size: Font size for analysis (defaults to FONT_SIZE from env)
            stroke_width: Width of text stroke
        """
        self.word_text = word_text
        self.word_spacing = word_spacing
        self.screensize = screensize
        self.font_size = font_size
        self.stroke_width = stroke_width
        
        # Calculate center position explicitly
        self.center_x = screensize[0] // 2
        self.center_y = screensize[1] // 2
        
        # Analyze the word boundaries
        self._analyze_boundaries()
        
        print(f"Word '{word_text}': boundaries {self.text_left} to {self.text_right}")
    
    def _analyze_boundaries(self):
        """Analyze the padded word text to find boundaries"""
        # Create a single-frame text clip with proper spacing and explicit positioning
        padded_text = TextClip(self.word_spacing,
                              color='white',
                              font=FONT_NAME,
                              bg_color='black',
                              kerning=FONT_KERNING,
                              fontsize=self.font_size,
                              method='label').set_position((self.center_x, self.center_y)).set_duration(0.1)
        
        # Create composite to get frame
        #temp_composite = CompositeVideoClip([padded_text], size=self.screensize)
        mask_frame = padded_text.get_frame(0)
        

        # Store the mask frame
        self.mask_frame = mask_frame

        #temp_composite.close()
        padded_text.close()
        
        # Find actual text boundaries by examining the mask frame
        gray_frame = np.mean(mask_frame, axis=2)  # Convert to grayscale
        text_pixels = gray_frame > 10  # Find non-black pixels
        
        # Find leftmost and rightmost text pixels
        text_cols = np.any(text_pixels, axis=0)  # Check each column
        self.text_left = np.argmax(text_cols) if np.any(text_cols) else 0
        self.text_right = len(text_cols) - 1 - np.argmax(text_cols[::-1]) if np.any(text_cols) else self.screensize[0]
    
    def create_wipe_mask(self, global_time, start_time, duration):
        """
        Create a wipe mask for this word at the given global time.
        
        Args:
            global_time: Current time in the overall video
            start_time: When this word's wipe should start
            duration: How long this word's wipe takes
            
        Returns:
            Mask frame for this word at this time
        """
        # Calculate local time for this word
        local_time = global_time - start_time
        
        # If before this word starts, return completely hidden mask
        if local_time < 0:
            hidden_mask = self.mask_frame.copy()
            hidden_mask[:, :] = 0  # Completely black (hidden)
            return hidden_mask
        
        # Calculate the reveal progress (0 to 1)
        # Complete the reveal at 96% of duration so full text is visible
        reveal_duration = duration * 0.96
        progress = min(local_time / reveal_duration, 1.0)
        
        # Calculate the current reveal position
        reveal_x = self.text_left + progress * (self.text_right - self.text_left)
        
        # Create a copy of the original mask
        wipe_mask = self.mask_frame.copy()
        
        # Hide everything to the right of reveal_x by setting it to black
        wipe_mask[:, round(reveal_x):] = 0  # Set to black
        
        return wipe_mask
    
    def create_wipe_mask_local(self, local_time, duration):
        """
        Create a wipe mask for this word using local time directly.
        
        Args:
            local_time: Time elapsed since this word's wipe should start (0 or positive)
            duration: How long this word's wipe takes
            
        Returns:
            Mask frame for this word at this local time
        """
        # If negative local time, return completely hidden mask
        if local_time < 0:
            hidden_mask = self.mask_frame.copy()
            hidden_mask[:, :] = 0  # Completely black (hidden)
            return hidden_mask
        
        # Calculate the reveal progress (0 to 1)
        # Complete the reveal at 96% of duration so full text is visible
        reveal_duration = duration * 0.96
        progress = min(local_time / reveal_duration, 1.0)
        
        # Calculate the current reveal position
        reveal_x = self.text_left + progress * (self.text_right - self.text_left)
        
        # Create a copy of the original mask
        wipe_mask = self.mask_frame.copy()
        
        # Hide everything to the right of reveal_x by setting it to black
        wipe_mask[:, round(reveal_x):] = 0  # Set to black
        
        return wipe_mask

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate karaoke video from alignment data')
    parser.add_argument('--audio', required=True, help='Path to audio file (instrumental or full song)')
    parser.add_argument('--alignment', required=True, help='Path to lyrics alignment JSON file from Viterbi')
    parser.add_argument('--output_dir', help='Directory for output files (defaults to alignment file directory)')
    parser.add_argument('--output_name', help='Name for output video file (defaults to alignment filename)')
    parser.add_argument('--resolution', default='360', 
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