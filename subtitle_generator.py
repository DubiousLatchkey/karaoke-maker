import json
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
import re

def load_alignment_data(alignment_file_path):
    """Load alignment data from JSON file"""
    try:
        with open(alignment_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading alignment data: {e}")
        return None

def format_time_for_ttml(seconds):
    """Convert seconds to TTML time format (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

def group_words_into_lines(words):
    """Group words into lines based on line_end markers or timing gaps"""
    lines = []
    current_line = []
    
    for word in words:
        current_line.append(word)
        
        # Check if this word ends a line
        if word.get('line_end', False):
            lines.append(current_line)
            current_line = []
    
    # Add any remaining words as the last line
    if current_line:
        lines.append(current_line)
    
    return lines

def create_karaoke_line_subtitles(line_words, line_idx):
    """Create karaoke-style subtitles for a single line with word-by-word color changes"""
    subtitle_entries = []
    
    if not line_words:
        return subtitle_entries
    
    # For each word in the line, create a subtitle entry
    for word_idx, current_word in enumerate(line_words):
        word_start = current_word.get('begin', current_word.get('start', 0))
        
        # Determine when this word's subtitle should end
        if word_idx < len(line_words) - 1:
            # Not the last word - end when the next word begins
            next_word = line_words[word_idx + 1]
            word_end = next_word.get('begin', next_word.get('start', word_start + 0.5))
        else:
            # Last word in line - end when the word actually ends
            word_end = current_word.get('end', current_word.get('end', word_start + 0.5))
        
        # Create the line text with different colors for sung/unsung words
        line_parts = []
        for i, word in enumerate(line_words):
            word_text = word.get('word', word.get('text', '')).strip()
            if not word_text:
                continue
                
            if i < word_idx:
                # Already sung words - green color
                line_parts.append(f'<span tts:color="lime">{word_text}</span>')
            elif i == word_idx:
                # Currently singing word - yellow color
                line_parts.append(f'<span tts:color="yellow">{word_text}</span>')
            else:
                # Not yet sung words - white color
                line_parts.append(f'<span tts:color="white">{word_text}</span>')
        
        # Create subtitle entry for this word timing
        entry = {
            'start_time': word_start,
            'end_time': word_end,
            'text': ' '.join(line_parts),
            'line_id': line_idx
        }
        subtitle_entries.append(entry)
    
    return subtitle_entries

def create_ttml_karaoke_subtitle(words, song_title="", artist=""):
    """Create karaoke-style TTML subtitle content with word-by-word color changes"""
    # Create root TTML element
    tt = Element('tt')
    tt.set('xmlns', 'http://www.w3.org/ns/ttml')
    tt.set('xmlns:tts', 'http://www.w3.org/ns/ttml#styling')
    tt.set('xml:lang', 'en')
    
    # Head section with metadata and styling
    head = SubElement(tt, 'head')
    
    # Metadata
    metadata = SubElement(head, 'metadata')
    if song_title:
        title = SubElement(metadata, 'title')
        title.text = song_title
    if artist:
        creator = SubElement(metadata, 'creator')
        creator.text = artist
    
    # Styling
    styling = SubElement(head, 'styling')
    
    # Base style
    base_style = SubElement(styling, 'style')
    base_style.set('xml:id', 'baseStyle')
    base_style.set('tts:fontFamily', 'Arial, sans-serif')
    base_style.set('tts:fontSize', '28px')
    base_style.set('tts:fontWeight', 'bold')
    base_style.set('tts:textAlign', 'center')
    base_style.set('tts:padding', '10px')
    
    # Sung word style
    sung_style = SubElement(styling, 'style')
    sung_style.set('xml:id', 'sungStyle')
    sung_style.set('tts:color', 'lime')
    
    # Current word style  
    current_style = SubElement(styling, 'style')
    current_style.set('xml:id', 'currentStyle')
    current_style.set('tts:color', 'yellow')
    
    # Unsung word style
    unsung_style = SubElement(styling, 'style')
    unsung_style.set('xml:id', 'unsungStyle')
    unsung_style.set('tts:color', 'white')
    
    # Body section
    body = SubElement(tt, 'body')
    div = SubElement(body, 'div')
    div.set('style', 'baseStyle')
    
    # Group words into lines
    lines = group_words_into_lines(words)
    
    # Create karaoke subtitles for each line
    for line_idx, line_words in enumerate(lines):
        karaoke_entries = create_karaoke_line_subtitles(line_words, line_idx)
        
        # Add each karaoke entry as a paragraph
        for entry_idx, entry in enumerate(karaoke_entries):
            p = SubElement(div, 'p')
            p.set('begin', format_time_for_ttml(entry['start_time']))
            p.set('end', format_time_for_ttml(entry['end_time']))
            
            # Create spans directly instead of parsing HTML-like text
            line_words = lines[entry['line_id']]
            current_word_idx = entry_idx  # This is the word currently being sung
            
            # Build the paragraph with proper spans
            for i, word in enumerate(line_words):
                word_text = word.get('word', word.get('text', '')).strip()
                if not word_text:
                    continue
                
                # Create span for this word
                span = SubElement(p, 'span')
                
                # Set color based on word position
                if i < current_word_idx:
                    span.set('tts:color', 'lime')  # Already sung
                elif i == current_word_idx:
                    span.set('tts:color', 'yellow')  # Currently singing
                else:
                    span.set('tts:color', 'white')  # Not yet sung
                    
                span.text = word_text
                
                # Add space after word (except last word)
                if i < len(line_words) - 1:
                    span.tail = ' '
    
    return tt

def create_ttml_subtitle(words, song_title="", artist=""):
    """Create TTML subtitle content from word timing data"""
    # Create root TTML element
    tt = Element('tt')
    tt.set('xmlns', 'http://www.w3.org/ns/ttml')
    tt.set('xmlns:tts', 'http://www.w3.org/ns/ttml#styling')
    tt.set('xml:lang', 'en')
    
    # Head section with metadata and styling
    head = SubElement(tt, 'head')
    
    # Metadata
    metadata = SubElement(head, 'metadata')
    if song_title:
        title = SubElement(metadata, 'title')
        title.text = song_title
    if artist:
        creator = SubElement(metadata, 'creator')
        creator.text = artist
    
    # Styling
    styling = SubElement(head, 'styling')
    style = SubElement(styling, 'style')
    style.set('xml:id', 'defaultStyle')
    style.set('tts:fontFamily', 'Arial, sans-serif')
    style.set('tts:fontSize', '24px')
    style.set('tts:color', 'white')
    style.set('tts:textAlign', 'center')
    
    # Body section
    body = SubElement(tt, 'body')
    div = SubElement(body, 'div')
    div.set('style', 'defaultStyle')
    
    # Group words into lines
    lines = group_words_into_lines(words)
    
    # Create subtitle entries for each line
    for line_idx, line_words in enumerate(lines):
        if not line_words:
            continue
            
        # Get timing for the entire line
        start_time = line_words[0].get('begin', line_words[0].get('start', 0))
        end_time = line_words[-1].get('end', line_words[-1].get('end', start_time + 1))
        
        # Create paragraph element
        p = SubElement(div, 'p')
        p.set('begin', format_time_for_ttml(start_time))
        p.set('end', format_time_for_ttml(end_time))
        
        # Add words to the line with individual timing
        line_text_parts = []
        for word in line_words:
            word_text = word.get('word', word.get('text', '')).strip()
            if word_text:
                line_text_parts.append(word_text)
        
        # Set the text content
        p.text = ' '.join(line_text_parts)
    
    return tt

def export_ttml_subtitle(alignment_file_path, output_path, song_title="", artist="", karaoke_style=True):
    """Export alignment data to TTML subtitle file"""
    try:
        # Load alignment data
        alignment_data = load_alignment_data(alignment_file_path)
        if not alignment_data:
            return False
        
        # Convert data to standard format
        words = []
        
        # Handle different alignment data formats
        if isinstance(alignment_data, list):
            words = alignment_data
        elif isinstance(alignment_data, dict) and 'segments' in alignment_data:
            for segment in alignment_data['segments']:
                if 'words' in segment:
                    words.extend(segment['words'])
        elif isinstance(alignment_data, dict) and 'words' in alignment_data:
            words = alignment_data['words']
        
        if not words:
            print("No word data found in alignment file")
            return False
        
        # Create TTML content - choose between karaoke and regular style
        if karaoke_style:
            ttml_root = create_ttml_karaoke_subtitle(words, song_title, artist)
        else:
            ttml_root = create_ttml_subtitle(words, song_title, artist)
        
        # Convert to pretty-printed XML string
        rough_string = tostring(ttml_root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Remove empty lines and fix XML declaration
        lines = [line for line in pretty_xml.split('\n') if line.strip()]
        pretty_xml = '\n'.join(lines)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        style_type = "karaoke-style" if karaoke_style else "regular"
        print(f"TTML {style_type} subtitle exported successfully: {output_path}")
        return True
        
    except Exception as e:
        print(f"Error exporting TTML subtitle: {e}")
        return False

def export_subtitle_from_project(project_dir, song_title="", artist="", karaoke_style=True):
    """Export subtitle from a project directory"""
    project_path = Path(project_dir)
    
    # Find alignment file
    alignment_file = None
    for file in project_path.iterdir():
        if file.name.endswith('project.json'):
            alignment_file = str(file)
            break
        if file.name.endswith('lyrics_alignment.json'):
            alignment_file = str(file)
            
    if not alignment_file:
        print("No alignment file found in project")
        return False
    
    # Create output path
    output_name = song_title if song_title else project_path.name
    style_suffix = "_karaoke_subtitles.ttml" if karaoke_style else "_subtitles.ttml"
    output_path = project_path / f"{output_name}{style_suffix}"
    
    # Export subtitle
    return export_ttml_subtitle(alignment_file, str(output_path), song_title, artist, karaoke_style) 