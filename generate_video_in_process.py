import os
import json
import multiprocessing
from pathlib import Path
from moviepy.editor import ColorClip, TextClip, CompositeVideoClip, AudioFileClip, VideoClip, concatenate_videoclips
import dotenv
dotenv.load_dotenv(dotenv_path='.env')

# Load font configurations from environment variables
FONT_NAME = os.getenv('FONT_NAME', 'Cascadia-Mono-Regular')
FONT_COLOR_ACTIVE = os.getenv('FONT_COLOR_ACTIVE', 'yellow')
FONT_COLOR_INACTIVE = os.getenv('FONT_COLOR_INACTIVE', 'white')
FONT_KERNING = int(os.getenv('FONT_KERNING', '1'))

def _video_generation_worker(pipe, instrumental_path, alignment_path, output_name, output_dir, resolution, use_wipe, song_title, artist):
    """Worker process for video generation"""
    try:
        from video_generator import KaraokeVideoGenerator
        
        # Initialize video generator
        generator = KaraokeVideoGenerator(output_dir, resolution)
        
        # Override print function to send through pipe
        def progress_callback(msg):
            pipe.send(('progress', msg))
            
        # Monkey patch print function
        import builtins
        original_print = builtins.print
        def custom_print(*args, **kwargs):
            msg = ' '.join(str(arg) for arg in args)
            pipe.send(('progress', msg))
            original_print(*args, **kwargs)
        builtins.print = custom_print
        
        try:
            # Generate video with metadata
            result = generator.generate(
                instrumental_path, 
                alignment_path, 
                output_name, 
                use_wipe,
                song_title=song_title,
                artist=artist
            )
            
            # Send success result
            pipe.send(('finished', result))
            
        finally:
            # Restore original print function
            builtins.print = original_print
            
    except Exception as e:
        # Send error
        pipe.send(('error', str(e)))
    finally:
        pipe.close()

def generate_video_in_process(instrumental_path, alignment_path, output_name, output_dir, resolution="1280x720", use_wipe=True, progress_callback=None, song_title=None, artist=None):
    """
    Generate video in a separate process with progress updates
    
    Args:
        instrumental_path (str): Path to instrumental audio
        alignment_path (str): Path to alignment JSON
        output_name (str): Name for output video
        output_dir (str): Directory for output
        resolution (str): Video resolution
        use_wipe (bool): Whether to use wipe transitions
        progress_callback (callable): Function to call with progress updates
        song_title (str): Title of the song for intro
        artist (str): Artist name for intro
        
    Returns:
        str: Path to generated video file
    """
    # Create pipe for communication
    parent_conn, child_conn = multiprocessing.Pipe()
    
    # Create and start process
    process = multiprocessing.Process(
        target=_video_generation_worker,
        args=(child_conn, instrumental_path, alignment_path, output_name, output_dir, resolution, use_wipe, song_title, artist)
    )
    process.start()
    
    # Monitor progress
    result = None
    while process.is_alive():
        if parent_conn.poll(0.1):  # Check for messages with timeout
            msg_type, msg_data = parent_conn.recv()
            
            if msg_type == 'progress' and progress_callback:
                progress_callback(msg_data)
            elif msg_type == 'finished':
                result = msg_data
            elif msg_type == 'error':
                raise Exception(msg_data)
    
    # Clean up
    process.join()
    parent_conn.close()
    
    return result 