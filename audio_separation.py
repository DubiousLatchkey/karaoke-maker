import os
import torch
from demucs.pretrained import get_model
from demucs.apply import apply_model
from demucs.audio import AudioFile, save_audio
import torchaudio

class AudioSeparator:
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = get_model("htdemucs")
        self.model.to(self.device)
        
    def separate(self, audio_path):
        """
        Separate audio into 4 tracks using HTDemucs:
        - Drums
        - Bass
        - Other (guitar, synth, etc.)
        - Vocals
        
        Also saves a combined instrumental track (drums + bass + other)
        
        Args:
            audio_path (str): Path to the input audio file
            
        Returns:
            dict: Dictionary containing paths to all separated tracks
        """
        # Load audio file
        wav = AudioFile(audio_path).read(streams=0, samplerate=self.model.samplerate, channels=self.model.audio_channels)
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()
        
        # Separate sources
        sources = apply_model(self.model, wav[None], device=self.device)[0]
        sources = sources * ref.std() + ref.mean()
        
        # Save separated tracks
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        output_paths = {}
        
        # Save each track with its correct label
        track_names = ['drums', 'bass', 'other', 'vocals']
        for i, name in enumerate(track_names):
            track_path = os.path.join(self.output_dir, f"{base_name}_{name}.wav").replace('\\', '/')
            os.makedirs(os.path.dirname(track_path), exist_ok=True)
            save_audio(sources[i], track_path, self.model.samplerate)
            output_paths[name] = track_path
        
        # Create and save combined instrumental track (drums + bass + other)
        instrumental = sources[0] + sources[1] + sources[2]  # Sum drums, bass, and other
        instrumental_path = os.path.join(self.output_dir, f"{base_name}_instrumental.wav").replace('\\', '/')
        save_audio(instrumental, instrumental_path, self.model.samplerate)
        output_paths['instrumental'] = instrumental_path
        
        return output_paths

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test audio separation')
    parser.add_argument('--input', required=True, help='Path to input audio file')
    parser.add_argument('--output_dir', required=True, help='Directory for output files')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Initialize separator
    separator = AudioSeparator(args.output_dir)
    
    # Process file
    print(f"Processing {args.input}...")
    output_paths = separator.separate(args.input)
    
    # Print output paths
    print("\nSeparated tracks:")
    for name, path in output_paths.items():
        print(f"{name.capitalize()}: {path}") 