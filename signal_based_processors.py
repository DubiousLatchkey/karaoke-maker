import os
import json
from pathlib import Path
from audio_separation import AudioSeparator
from forced_alignment import LyricsAligner
from video_generator import KaraokeVideoGenerator
from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, AudioFileClip, VideoClip, concatenate_videoclips
import dotenv
dotenv.load_dotenv(dotenv_path='.env')

# Load font configurations from environment variables
FONT_NAME = os.getenv('FONT_NAME', 'Cascadia-Mono-Regular')
FONT_COLOR_ACTIVE = os.getenv('FONT_COLOR_ACTIVE', 'yellow')
FONT_COLOR_INACTIVE = os.getenv('FONT_COLOR_INACTIVE', 'white')
FONT_KERNING = int(os.getenv('FONT_KERNING', '1'))


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

def run_process_mode_with_signals(input_dir, output_dir, progress_signal):
    """
    Run the processing steps without video generation, using progress signals:
    1. Vocal separation using Demucs
    2. Forced alignment with Viterbi algorithm
    
    Args:
        input_dir: Directory containing audio and lyrics files
        output_dir: Directory for output files
        progress_signal: Signal to emit progress messages
    
    Returns:
        dict: Paths to all generated files
    """
    try:
        progress_signal.emit("=== KARAOKE MAKER - PROCESS MODE ===\n")
        
        # Find input files
        audio_file, lyrics_file = find_input_files(input_dir)
        if not audio_file or not lyrics_file:
            progress_signal.emit("Error: Could not find both audio and lyrics files in input directory")
            progress_signal.emit(f"Audio file: {audio_file}")
            progress_signal.emit(f"Lyrics file: {lyrics_file}")
            return None
        
        # Determine output name
        base_name = audio_file.stem
        progress_signal.emit(f"Processing: {audio_file.name}")
        progress_signal.emit(f"Lyrics: {lyrics_file.name}")
        progress_signal.emit(f"Output name: {base_name}\n")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        progress_signal.emit("Initializing processing components...")
        separator = AudioSeparator(str(output_path))
        aligner = LyricsAligner(str(output_path))
        
        # Step 1: Vocal Separation
        progress_signal.emit("\n--- STEP 1: VOCAL SEPARATION ---")
        progress_signal.emit("Separating vocals from instrumental using HTDemucs...")
        separation_results = separator.separate(str(audio_file))
        
        vocal_path = separation_results['vocals']
        instrumental_path = separation_results['instrumental']
        
        progress_signal.emit(f"✓ Vocals extracted: {vocal_path}")
        progress_signal.emit(f"✓ Instrumental created: {instrumental_path}")
        
        # Step 2: Forced Alignment
        progress_signal.emit("\n--- STEP 2: FORCED ALIGNMENT + VITERBI ---")
        progress_signal.emit("Running ASR transcription...")
        
        # Generate ASR alignment
        asr_alignment_path = aligner.run_asr(vocal_path)
        progress_signal.emit(f"✓ ASR transcription complete: {asr_alignment_path}")
        
        progress_signal.emit("Running Viterbi alignment with lyrics...")
        # Align ASR to lyrics using Viterbi
        final_alignment_path = aligner.align_to_lyrics(asr_alignment_path, str(lyrics_file))
        progress_signal.emit(f"✓ Viterbi alignment complete: {final_alignment_path}")
        
        # Summary
        progress_signal.emit("\n=== PROCESS COMPLETE ===")
        results = {
            'original_audio': str(audio_file),
            'lyrics': str(lyrics_file),
            'vocals': vocal_path,
            'instrumental': instrumental_path,
            'asr_alignment': asr_alignment_path,
            'final_alignment': final_alignment_path,
            'base_name': base_name
        }
        
        progress_signal.emit("Generated files:")
        for key, path in results.items():
            if key not in ['original_audio', 'lyrics', 'base_name']:
                progress_signal.emit(f"  {key}: {path}")
        
        return results
        
    except Exception as e:
        progress_signal.emit(f"Error during processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

class SignalBasedVideoGenerator(KaraokeVideoGenerator):
    """Video generator that uses progress signals instead of print statements"""
    
    def __init__(self, output_dir, resolution="1280x720", progress_signal=None):
        super().__init__(output_dir, resolution)
        self.progress_signal = progress_signal
        
    def generate(self, instrumental_path, alignment_path, output_name, use_wipe=True):
        """
        Generate karaoke video with timed lyrics in karaoke style
        
        Args:
            instrumental_path (str): Path to the instrumental audio
            alignment_path (str): Path to the alignment JSON file with line_end markers
            output_name (str): Name for the output video file
            use_wipe (bool): Whether to use wipe transitions instead of progressive highlighting
            
        Returns:
            str: Path to the generated video file
        """
        if self.progress_signal:
            self.progress_signal.emit(f"Loading alignment data from: {alignment_path}")
        
        # Load alignment data
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
            
        if self.progress_signal:
            self.progress_signal.emit(f"Loaded {len(alignment_data)} word alignments")
        
        # Load audio
        if self.progress_signal:
            self.progress_signal.emit(f"Loading audio from: {instrumental_path}")
        audio = AudioFileClip(instrumental_path)
        duration = audio.duration
        if self.progress_signal:
            self.progress_signal.emit(f"Audio duration: {duration:.2f} seconds")
        
        # Load metadata to get song title and artist
        metadata_path = Path(alignment_path).parent / "metadata.json"
        song_title = output_name
        artist = ""
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    song_title = metadata.get('name', output_name)
                    artist = metadata.get('artist', '')
            except Exception as e:
                if self.progress_signal:
                    self.progress_signal.emit(f"Warning: Could not load metadata: {e}")
        
        # Group words into lines based on line_end markers
        lines = self._group_words_into_lines(alignment_data)
        if self.progress_signal:
            self.progress_signal.emit(f"Grouped into {len(lines)} karaoke lines")
        
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
                if self.progress_signal:
                    self.progress_signal.emit(f"  Positioned {clip_type} line {i+1} at y={y_position}")
            
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
                    if self.progress_signal:
                        self.progress_signal.emit(f"Added break message: {break_text}")
        
        if self.progress_signal:
            self.progress_signal.emit(f"Created {len(line_clips)} positioned line clips")
        
        # Handle intro based on timing of first line
        first_line_start = lines[0]['start'] if lines else 0
        intro_clips = []
        
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
            if self.progress_signal:
                self.progress_signal.emit(f"Added intro title during musical intro")
        else:
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
            if self.progress_signal:
                self.progress_signal.emit(f"Created separate 5-second intro clip")
        
        # Combine all clips
        mode_name = "wipe" if use_wipe else "karaoke"
        if self.progress_signal:
            self.progress_signal.emit(f"Compositing {mode_name} video...")
        final_video = CompositeVideoClip([background] + line_clips)
        
        # Add audio
        final_video = final_video.set_audio(audio)
        
        # If we have a separate intro clip, concatenate it with the main video
        if intro_clips:
            intro_video = CompositeVideoClip([ColorClip(size=self.resolution, color=(0, 0, 0), duration=5)] + intro_clips)
            final_video = concatenate_videoclips([intro_video, final_video])
            if self.progress_signal:
                self.progress_signal.emit("Concatenated intro clip with main video")
        
        # Write output file
        output_path = os.path.join(self.output_dir, f"{output_name}.mp4")
        if self.progress_signal:
            self.progress_signal.emit(f"Writing {mode_name} video to: {output_path}")
        
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
        
        if self.progress_signal:
            self.progress_signal.emit(f"Karaoke {mode_name} video generation complete!")
        return output_path 