import os
import unicodedata
import torch
import torchaudio
import json
import numpy as np
from pathlib import Path
import re
import whisperx
import gc
import nltk
from nltk.metrics.distance import edit_distance
import heapq

torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

def viterbi_many_to_one_alignment(asr_tokens, lyrics_tokens, k=3):
    """
    Performs many-to-one alignment between ASR tokens and lyrics tokens using Viterbi algorithm
    with Levenshtein distance as the metric.
    
    Args:
        asr_tokens (list): List of ASR tokens (words)
        lyrics_tokens (list): List of lyrics tokens (words)
        k (int): Maximum number of ASR tokens to consider in each mapping
    
    Returns:
        list: List of mappings, where each mapping is a tuple (asr_indices, lyrics_index)
        representing the aligned token groups
    """
    print(f"Starting Viterbi many-to-one alignment with k={k}")
    print(f"ASR tokens: {len(asr_tokens)}, Lyrics tokens: {len(lyrics_tokens)}")
    
    # Initialize states and backpointers
    # States: (i, j) where i is the index in asr_tokens, j is the index in lyrics_tokens
    states = [(0, 0)]
    scores = {(0, 0): 0}
    backpointers = {}
    
    # Process states in topological order
    while states:
        # Get state with lowest score
        i, j = min(states, key=lambda s: scores[s])
        states.remove((i, j))
        current_score = scores[(i, j)]
        
        # print(f"\n--- Processing state ({i}, {j}) with score {current_score:.3f} ---")
        
        # Terminal state
        if i == len(asr_tokens) and j == len(lyrics_tokens):
            print("Reached terminal state")
            continue
        
        # Try different many-to-one mappings: many ASR tokens to a single lyric token
        for asr_count in range(1, min(k+1, len(asr_tokens) - i + 1)):
            # Fixed lyrics count to 1 for many-to-one mapping
            lyrics_count = 1
            
            if i + asr_count <= len(asr_tokens) and j + lyrics_count <= len(lyrics_tokens):
                # Get the text segments
                asr_segment = " ".join(asr_tokens[i:i+asr_count])
                lyrics_segment = lyrics_tokens[j]  # Just a single lyrics token
                
                # Calculate Levenshtein distance as a cost
                distance = edit_distance(asr_segment.lower(), lyrics_segment.lower())
                
                # Normalize by max length to get a fairer comparison across different segment sizes
                max_len = max(len(asr_segment), len(lyrics_segment))
                normalized_distance = distance / max_len if max_len > 0 else 0
                
                # New state and its score
                new_state = (i + asr_count, j + lyrics_count)
                new_score = current_score + normalized_distance
                
                # print(f"  Trying: ASR[{i}:{i+asr_count}] = '{asr_segment}' -> Lyrics[{j}] = '{lyrics_segment}'")
                # print(f"    Edit distance: {distance}, Max length: {max_len}, Normalized: {normalized_distance:.3f}")
                # print(f"    New state: {new_state}, New score: {new_score:.3f}")
                
                # Update if this is a better path to the new state
                if new_state not in scores or new_score < scores[new_state]:
                    old_score = scores.get(new_state, float('inf'))
                    scores[new_state] = new_score
                    backpointers[new_state] = ((i, j), (asr_count, lyrics_count))
                    if new_state not in states:
                        states.append(new_state)
                    #print(f"    ✓ Updated state {new_state}: {old_score:.3f} -> {new_score:.3f}")
                else:
                    # print(f"    ✗ Not better than existing score {scores[new_state]:.3f}")
                    pass
        
        # Allow skipping ASR tokens (deletion) - when ASR has extra words
        if i + 1 <= len(asr_tokens):
            skip_penalty = 0.5  # Penalty for skipping ASR tokens
            new_state = (i + 1, j)
            new_score = current_score + skip_penalty
            
            if new_state not in scores or new_score < scores[new_state]:
                old_score = scores.get(new_state, float('inf'))
                scores[new_state] = new_score
                backpointers[new_state] = ((i, j), ('skip_asr', 0))
                if new_state not in states:
                    states.append(new_state)
                #print(f"    ✓ Skip ASR[{i}] '{asr_tokens[i]}'")
        
        # Allow skipping lyrics tokens (insertion) - when lyrics have words not in ASR
        if j + 1 <= len(lyrics_tokens):
            skip_penalty = 1.0  # Higher penalty for skipping lyrics tokens
            new_state = (i, j + 1)
            new_score = current_score + skip_penalty
            
            if new_state not in scores or new_score < scores[new_state]:
                old_score = scores.get(new_state, float('inf'))
                scores[new_state] = new_score
                backpointers[new_state] = ((i, j), ('skip_lyrics', 0))
                if new_state not in states:
                    states.append(new_state)
                #print(f"    ✓ Skip Lyrics[{j}] '{lyrics_tokens[j]}'")
    
    # Reconstruct the alignment from backpointers
    alignment = []
    state = (len(asr_tokens), len(lyrics_tokens))
    
    # Check if we found a path to the end
    if state not in backpointers:
        print("Warning: Could not find complete alignment path")
        print(f"Final states available: {list(scores.keys())}")
        return []
        
    print(f"\n--- Reconstructing alignment from final state {state} ---")
    while state != (0, 0):
        prev_state, action = backpointers[state]
        i, j = prev_state
        
        if isinstance(action, tuple) and len(action) == 2:
            if action[0] == 'skip_asr':
                print(f"  Skip ASR[{i}] '{asr_tokens[i]}'")
            elif action[0] == 'skip_lyrics':
                print(f"  Skip Lyrics[{j}] '{lyrics_tokens[j]}'")
            else:
                asr_count, lyrics_count = action
                asr_indices = list(range(i, i + asr_count))
                lyrics_index = j  # Single lyrics index
                
                asr_words = [asr_tokens[idx] for idx in asr_indices]
                lyrics_word = lyrics_tokens[lyrics_index]
                print(f"  Mapping: ASR {asr_indices} {asr_words} -> Lyrics[{lyrics_index}] '{lyrics_word}'")
                
                alignment.append((asr_indices, lyrics_index))
        
        state = prev_state
    
    # Reverse to get correct order
    alignment.reverse()
    
    print(f"Alignment complete. Found {len(alignment)} mappings.")
    return alignment

class LyricsAligner:
    def __init__(self, output_dir):
        print(f"Initializing LyricsAligner with output directory: {output_dir}")
        self.output_dir = Path(output_dir)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {self.device}")
        
    def run_asr(self, audio_path):
        """
        Run WhisperX on audio to generate ASR and alignment
        
        Args:
            audio_path (str): Path to audio file
            lyrics_path (str, optional): Path to lyrics file, not required for ASR
            
        Returns:
            str: Path to the alignment JSON file
        """
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
        
        # Create word-level timestamps using WhisperX alignment
        print("\nAligning with WhisperX...")
        model_a, metadata = whisperx.load_align_model(language_code=transcription["language"], device=self.device)
        aligned_result = whisperx.align(
            transcription["segments"], model_a, metadata, audio_nparray, self.device, return_char_alignments=True
        )
        
        # Save alignment data
        alignment_path = self.output_dir / f"{audio_path.stem}_alignment.json"
        print(f"\nSaving ASR alignment data to: {alignment_path}")
        with open(alignment_path, 'w', encoding='utf-8') as f:
            json.dump(aligned_result, f, indent=2)
            
        return str(alignment_path)


    def align_to_lyrics(self, asr_alignment_path, lyrics_path, k=3):
        """
        Align lyrics with ASR output using Viterbi many-to-one alignment
        
        Args:
            asr_alignment_path (str): Path to ASR alignment JSON file from WhisperX
            lyrics_path (str): Path to lyrics file
            k (int): Parameter for many-to-one mapping in Viterbi algorithm (max ASR tokens per lyric token)
            
        Returns:
            str: Path to the alignment JSON file
        """
        # Load ASR alignment file
        print(f"\nLoading ASR alignment from: {asr_alignment_path}")
        with open(asr_alignment_path, 'r', encoding='utf-8') as f:
            asr_data = json.load(f)
        
        # Read lyrics
        with open(lyrics_path, 'r', encoding='utf-8') as f:
            lyrics = f.read()

        lyrics = lyrics.replace("’", "'").replace("“", '"').replace("”", '"')
        
        # Tokenize lyrics into words
        lyrics_tokens = re.findall(r"\b[a-z']+\b", lyrics.lower())
        print(f"Lyrics tokens preview: {lyrics_tokens[:10]}")
        print(f"Lyrics tokens: {len(lyrics_tokens)}")
        
        # Extract ASR tokens and their timing information
        asr_tokens = []
        asr_token_timings = []
        
        # Process segments from ASR alignment
        for segment in asr_data["segments"]:
            if "words" in segment:
                for word in segment["words"]:
                    if "word" in word and "start" in word and "end" in word:
                        asr_tokens.append(word["word"].lower())
                        asr_token_timings.append({
                            "text": word["word"].lower(),
                            "start": word["start"],
                            "end": word["end"]
                        })
        
        print(f"ASR tokens extracted: {len(asr_tokens)}")
        
        # Align using Viterbi algorithm
        print("\nPerforming Viterbi alignment...")
        alignment = viterbi_many_to_one_alignment(asr_tokens, lyrics_tokens, k)
        
        # Map the Viterbi alignment to timings
        print("\nMapping Viterbi alignment to timings...")
        lyrics_alignment = []
        
        # Process all lyrics tokens in order
        for lyrics_idx, lyrics_token in enumerate(lyrics_tokens):
            # Find if this lyrics token was aligned to any ASR tokens
            matching_alignment = None
            for asr_indices, l_idx in alignment:
                if l_idx == lyrics_idx:
                    matching_alignment = asr_indices
                    break
            
            # Create entry for this lyrics token
            timing_entry = {
                "text": lyrics_token,
                "index": lyrics_idx
            }
            
            # If we found a matching alignment
            if matching_alignment and matching_alignment:
                # Get the ASR tokens that matched
                matching_asr_tokens = [asr_tokens[idx] for idx in matching_alignment if idx < len(asr_tokens)]
                timing_entry["asr_tokens"] = matching_asr_tokens
                
                # Find earliest start time and latest end time
                start_times = []
                end_times = []
                for idx in matching_alignment:
                    if idx < len(asr_token_timings):
                        start_times.append(asr_token_timings[idx]["start"])
                        end_times.append(asr_token_timings[idx]["end"])
                
                if start_times:
                    timing_entry["begin"] = min(start_times)
                    timing_entry["end"] = max(end_times)
                    timing_entry["asr_indices"] = matching_alignment
                else:
                    # No timing information found
                    timing_entry["begin"] = None
                    timing_entry["end"] = None
                    timing_entry["asr_indices"] = []
            else:
                # No alignment found for this lyrics token
                timing_entry["begin"] = None
                timing_entry["end"] = None
                timing_entry["asr_tokens"] = []
                timing_entry["asr_indices"] = []
            
            # Add to the alignment list
            lyrics_alignment.append(timing_entry)
        
        # Fill in missing timing information by interpolation
        print("\nInterpolating missing timing information...")
        self._interpolate_missing_timings(lyrics_alignment)
                
        # Save alignment data
        output_path = self.output_dir / f"{Path(asr_alignment_path).stem}_lyrics_alignment.json"
        print(f"\nSaving lyrics alignment data to: {output_path}")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(lyrics_alignment, f, indent=2)
            
        return str(output_path)
        
    def _interpolate_missing_timings(self, alignment):
        """
        Interpolate missing timing information in the alignment
        
        Args:
            alignment: List of alignment entries
        """
        # First, find all entries with valid timing information
        valid_indices = [i for i, entry in enumerate(alignment) if entry["begin"] is not None and entry["end"] is not None]
        
        if not valid_indices:
            print("Warning: No valid timing information found for interpolation")
            return
            
        # Interpolate missing timings
        for i in range(len(alignment)):
            if alignment[i]["begin"] is None or alignment[i]["end"] is None:
                # Find nearest indices with valid timing before and after current index
                prev_valid = None
                next_valid = None
                
                for j in valid_indices:
                    if j < i:
                        prev_valid = j
                    if j > i and next_valid is None:
                        next_valid = j
                        break
                
                # Interpolate based on available information
                if prev_valid is not None and next_valid is not None:
                    # Interpolate between two valid points
                    prev_time = alignment[prev_valid]["end"]
                    next_time = alignment[next_valid]["begin"]
                    total_tokens = next_valid - prev_valid - 1
                    if total_tokens > 0:
                        duration_per_token = (next_time - prev_time) / (total_tokens + 1)
                        position = i - prev_valid
                        alignment[i]["begin"] = prev_time + position * duration_per_token
                        alignment[i]["end"] = prev_time + (position + 1) * duration_per_token
                        alignment[i]["interpolated"] = True
                elif prev_valid is not None:
                    # Use the end of previous as start, and add small duration
                    alignment[i]["begin"] = alignment[prev_valid]["end"]
                    alignment[i]["end"] = alignment[i]["begin"] + 0.1  # Default duration of 100ms
                    alignment[i]["interpolated"] = True
                elif next_valid is not None:
                    # Use the beginning of next as end, and subtract small duration
                    alignment[i]["end"] = alignment[next_valid]["begin"]
                    alignment[i]["begin"] = alignment[i]["end"] - 0.1  # Default duration of 100ms
                    alignment[i]["interpolated"] = True

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Whisper-based lyrics alignment')
    parser.add_argument('--mode', choices=['asr', 'viterbi'], required=True,
                        help='Operation mode: "asr" to run WhisperX on audio, "viterbi" to align ASR output with lyrics')
    parser.add_argument('--input', required=True, 
                        help='Path to input file: audio file for ASR mode, alignment JSON for Viterbi mode')
    parser.add_argument('--lyrics', help='Path to lyrics text file')
    parser.add_argument('--k', type=int, default=3, help='K parameter for Viterbi alignment (default: 3)')
    args = parser.parse_args()
    
    # Use the input file's directory as the output directory
    output_dir = str(Path(args.input).parent)
    
    # Validate arguments based on mode
    if args.mode == 'viterbi' and not args.lyrics:
        print("Error: Lyrics file (--lyrics) is required for Viterbi mode")
        exit(1)
    
    # Initialize aligner
    aligner = LyricsAligner(output_dir)
    
    # Process files based on mode
    if args.mode == 'asr':
        print(f"\nRunning ASR alignment on audio: {args.input}")
        alignment_path = aligner.run_asr(args.input)
        print(f"\nASR alignment complete. Results saved to: {alignment_path}")
        print(f"Now you can run Viterbi alignment with: --mode viterbi --input {alignment_path} --lyrics <lyrics_file>")
    
    elif args.mode == 'viterbi':
        print(f"\nRunning Viterbi alignment between ASR file and lyrics")
        alignment_path = aligner.align_to_lyrics(args.input, args.lyrics, k=args.k)
        
        # Load and print alignment results
        print("\nLoading final alignment results...")
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)
        
        print("\nAlignment Results Summary:")
        print(f"Total alignments: {len(alignment_data)}")
        print("\nSample of aligned words:")
        for item in alignment_data[:5]:
            print(f"\nText: {item.get('text', '')}")
            print(f"Start: {item.get('begin', 'None') if item.get('begin') is None else item.get('begin', ''):.2f}s")
            print(f"End: {item.get('end', 'None') if item.get('end') is None else item.get('end', ''):.2f}s")
            
        print(f"\nViterbi alignment complete. Results saved to: {alignment_path}") 