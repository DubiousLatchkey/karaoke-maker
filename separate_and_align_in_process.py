import os
import json
import multiprocessing
from pathlib import Path
import dotenv
dotenv.load_dotenv(dotenv_path='.env')

def _separation_alignment_worker(pipe, input_dir, output_dir):
    """Worker process for audio separation and alignment"""
    try:
        # Set working directory to the script's directory
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
        # Reload environment variables
        dotenv.load_dotenv(dotenv_path='.env')
        
        from main import run_process_mode
        
        # Override print function to send through pipe
        import builtins
        original_print = builtins.print
        def custom_print(*args, **kwargs):
            msg = ' '.join(str(arg) for arg in args)
            pipe.send(('progress', msg))
            original_print(*args, **kwargs)
        builtins.print = custom_print
        
        try:
            # Run audio separation and alignment
            result = run_process_mode(input_dir, output_dir)
            
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

def separate_and_align_in_process(input_dir, output_dir, progress_callback=None):
    """
    Run audio separation and alignment in a separate process with progress updates
    
    Args:
        input_dir (str): Directory containing input audio files
        output_dir (str): Directory for output files
        progress_callback (callable): Function to call with progress updates
        
    Returns:
        dict: Results from audio separation and alignment
    """
    # Create pipe for communication
    parent_conn, child_conn = multiprocessing.Pipe()
    
    # Create and start process
    process = multiprocessing.Process(
        target=_separation_alignment_worker,
        args=(child_conn, input_dir, output_dir)
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