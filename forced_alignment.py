import os
import torch
import torchaudio
import json
import numpy as np
from pathlib import Path
import re
import whisperx
import gc

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

class LyricsAligner:
    def __init__(self, output_dir):
        print(f"Initializing LyricsAligner with output directory: {output_dir}")
        self.output_dir = Path(output_dir)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")
        
    def align(self, audio_path, lyrics_path):
        """
        Align lyrics with audio using Whisper for forced alignment
        
        Args:
            audio_path (str): Path to audio file
            lyrics_path (str): Path to lyrics file
            
        Returns:
            str: Path to the alignment JSON file
        """
        # Read lyrics
        with open(lyrics_path, 'r', encoding='utf-8') as f:
            lyrics = f.read()
            
        print("\nLyrics preview: ", lyrics[:100])
        print(f"Total lyrics length: {len(lyrics)} characters")
        
        audio_path = Path(audio_path)
        print(f"\nProcessing audio file: {audio_path}")

        # Load audio and convert to mono
        audio, sr = torchaudio.load(str(audio_path))
        if audio.shape[0] > 1:
            audio = torch.mean(audio, dim=0, keepdim=True)
        
        # Resample to 16kHz if needed
        if sr != 16000:
            print(f"Resampling audio from {sr}Hz to 16kHz")
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=16000)
            audio = resampler(audio)
            sr = 16000
            
        audio_nparray = audio.squeeze().numpy()
        
        # Use whisperx for transcription (for reference)
        print("\nGenerating transcription...")
        model = whisperx.load_model("medium", self.device)
        transcription = model.transcribe(str(audio_path), language="en")
        
        # Save transcription data
        transcription_path = self.output_dir / f"{audio_path.stem}_transcription.json"
        print(f"\nSaving transcription data to: {transcription_path}")
        with open(transcription_path, 'w', encoding='utf-8') as f:
            json.dump(transcription, f, indent=2)
        
        model_a, metadata = whisperx.load_align_model(language_code=transcription["language"], device=self.device)
        transcription = whisperx.align(
            transcription["segments"], model_a, metadata, audio_nparray, self.device, return_char_alignments=True
        )
        
        # Process alignment results
        print("\nProcessing alignment results...")
        word_timings = transcription
        # for segment in transcription["segments"]:
        #     for word in segment["words"]:
        #         word_timings.append({
        #             'text': word["word"],
        #             'begin': word["start"],
        #             'end': word["end"],
        #             'confidence': word.get("score", 1.0)  # Default confidence of 1.0 if not provided
        #         })
            
        # Save alignment data
        output_path = self.output_dir / f"{audio_path.stem}_alignment.json"
        print(f"\nSaving alignment data to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(word_timings, f, indent=2)
            
        return str(output_path)
        
    def forced_align_with_lyrics(self, audio_path, lyrics_path):
        """
        Perform forced alignment using lyrics as the reference text
        
        Args:
            audio_path (str): Path to audio file
            lyrics_path (str): Path to lyrics file
            
        Returns:
            str: Path to the alignment JSON file
        """
        # Read lyrics
        with open(lyrics_path, 'r', encoding='utf-8') as f:
            lyrics = f.read()
            
        audio_path = Path(audio_path)
        print(f"\nPerforming forced alignment with provided lyrics")
        
        # Load whisper model
        print("\nLoading Whisper model...")
        model = whisper.load_model("medium", self.device)
        
        model_a, metadata = whisper.load_align_model(language_code="en", device=self.device)

        result = model.transcribe(str(audio_path), language="en")

        result = whisper.align(result["segments"], model_a, metadata, str(audio_path), self.device)

        
            
        # Process alignment results
        print("\nProcessing alignment results...")
        word_timings = []
        for segment in result["segments"]:
            for word in segment["words"]:
                word_timings.append({
                    'text': word["word"],
                    'begin': word["start"],
                    'end': word["end"],
                    'confidence': word.get("score", 1.0)  # Default confidence of 1.0 if not provided
                })
            
        print(f"Generated {len(word_timings)} word timings")
        if word_timings:
            print("\nFirst few word timings:")
            for word in word_timings[:3]:
                print(f"Word: {word['text']}")
                print(f"  Start: {word['begin']:.2f}s")
                print(f"  End: {word['end']:.2f}s")
                print(f"  Confidence: {word.get('confidence', 'N/A')}")
            
        # Save alignment data
        output_path = self.output_dir / f"{audio_path.stem}_alignment.json"
        print(f"\nSaving alignment data to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(word_timings, f, indent=2)
            
        return str(output_path)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Whisper-based forced alignment')
    parser.add_argument('--audio', required=True, help='Path to vocal audio file')
    parser.add_argument('--lyrics', required=True, help='Path to lyrics text file')
    parser.add_argument('--output_dir', required=True, help='Directory for output files')
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize aligner
    aligner = LyricsAligner(args.output_dir)
    
    # Process files
    print(f"\nStarting alignment process...")
    alignment_path = aligner.align(args.audio, args.lyrics)
    
    # Load and print alignment results
    print("\nLoading final alignment results...")
    with open(alignment_path, 'r', encoding='utf-8') as f:
        alignment_data = json.load(f)
    
    print("\nAlignment Results Summary:")
    print(f"Total words aligned: {len(alignment_data)}")
    print("\nSample of aligned words:")
    for word in alignment_data[:5]:
        print(f"\nWord: {word['text']}")
        print(f"Start: {word['begin']:.2f}s")
        print(f"End: {word['end']:.2f}s")
        print(f"Confidence: {word.get('confidence', 'N/A')}") 