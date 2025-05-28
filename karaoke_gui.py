import sys
import os
import json
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                             QWidget, QPushButton, QFileDialog, QLabel, QSlider, 
                             QListWidget, QListWidgetItem, QSplitter, QTextEdit,
                             QProgressBar, QFrame, QSpacerItem, QSizePolicy, QDoubleSpinBox,
                             QCheckBox, QDialog, QLineEdit, QDialogButtonBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QKeySequence
import sounddevice as sd
import soundfile as sf
import numpy as np
import threading
import time
from audio_timeline_widget import AudioTimelineWidget
import shutil

class ProjectPropertiesDialog(QDialog):
    """Dialog for creating or editing project properties"""
    
    def __init__(self, parent=None, project_data=None):
        super().__init__(parent)
        self.project_data = project_data or {}
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Project Properties")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout()
        
        # Song name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Song Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(self.project_data.get('name', ''))
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # Artist
        artist_layout = QHBoxLayout()
        artist_layout.addWidget(QLabel("Artist:"))
        self.artist_edit = QLineEdit()
        self.artist_edit.setText(self.project_data.get('artist', ''))
        artist_layout.addWidget(self.artist_edit)
        layout.addLayout(artist_layout)
        
        # Audio file
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel("Audio File:"))
        self.audio_path_edit = QLineEdit()
        self.audio_path_edit.setText(self.project_data.get('audio_file', ''))
        self.audio_path_edit.setReadOnly(True)
        audio_layout.addWidget(self.audio_path_edit)
        
        browse_audio_btn = QPushButton("Browse...")
        browse_audio_btn.clicked.connect(self.browse_audio_file)
        audio_layout.addWidget(browse_audio_btn)
        layout.addLayout(audio_layout)
        
        # Lyrics file
        lyrics_layout = QHBoxLayout()
        lyrics_layout.addWidget(QLabel("Lyrics File:"))
        self.lyrics_path_edit = QLineEdit()
        self.lyrics_path_edit.setText(self.project_data.get('lyrics_file', ''))
        self.lyrics_path_edit.setReadOnly(True)
        lyrics_layout.addWidget(self.lyrics_path_edit)
        
        browse_lyrics_btn = QPushButton("Browse...")
        browse_lyrics_btn.clicked.connect(self.browse_lyrics_file)
        lyrics_layout.addWidget(browse_lyrics_btn)
        layout.addLayout(lyrics_layout)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
        
    def browse_audio_file(self):
        """Open file dialog to select audio file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            str(Path.home()),
            "Audio Files (*.mp3 *.wav *.flac *.m4a *.aac)"
        )
        if file_path:
            self.audio_path_edit.setText(file_path)
            
    def browse_lyrics_file(self):
        """Open file dialog to select lyrics file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Lyrics File",
            str(Path.home()),
            "Text Files (*.txt)"
        )
        if file_path:
            self.lyrics_path_edit.setText(file_path)
            
    def get_project_data(self):
        """Get the project data from the dialog fields"""
        return {
            'name': self.name_edit.text().strip(),
            'artist': self.artist_edit.text().strip(),
            'audio_file': self.audio_path_edit.text(),
            'lyrics_file': self.lyrics_path_edit.text()
        }

class AudioPlayer:
    """Audio player using sounddevice for reliable playback and seeking"""
    
    def __init__(self):
        self.audio_file = None
        self.audio_data = None
        self.sample_rate = None
        self.audio_length = 0
        self.is_playing = False
        self.is_paused = False
        self.position = 0
        self.start_time = 0
        self.playback_thread = None
        self.stop_event = threading.Event()
        
    def load_audio(self, file_path):
        """Load an audio file"""
        try:
            self.audio_file = file_path
            # Load audio using soundfile
            self.audio_data, self.sample_rate = sf.read(file_path)
            
            # Convert to stereo if mono
            if len(self.audio_data.shape) == 1:
                self.audio_data = np.column_stack((self.audio_data, self.audio_data))
            
            self.audio_length = len(self.audio_data) / self.sample_rate
            print(f"Loaded audio: {self.audio_length:.2f} seconds, {self.sample_rate}Hz")
            return True
        except Exception as e:
            print(f"Error loading audio: {e}")
            return False
    
    def _playback_worker(self, start_sample):
        """Worker thread for audio playback"""
        try:
            # Calculate the audio slice to play
            audio_slice = self.audio_data[start_sample:]
            
            # Play the audio slice
            sd.play(audio_slice, self.sample_rate)
            
            # Wait for playback to finish or stop event
            while sd.get_stream().active and not self.stop_event.is_set():
                time.sleep(0.01)
                
        except Exception as e:
            print(f"Error in playback worker: {e}")
        finally:
            # Clean up
            if not self.stop_event.is_set():
                # Playback finished naturally
                self.is_playing = False
                self.is_paused = False
                self.position = self.audio_length
    
    def play(self, start_position=None):
        """Start playing audio from current or specified position"""
        if self.audio_data is None:
            return False
            
        try:
            # Stop any current playback
            self.stop()
            
            if start_position is not None:
                self.position = max(0, min(start_position, self.audio_length))
            
            # Calculate start sample
            start_sample = int(self.position * self.sample_rate)
            
            # Reset stop event
            self.stop_event.clear()
            
            # Start playback in a separate thread
            self.playback_thread = threading.Thread(
                target=self._playback_worker, 
                args=(start_sample,),
                daemon=True
            )
            
            self.is_playing = True
            self.is_paused = False
            self.start_time = time.time() - self.position
            
            self.playback_thread.start()
            print(f"Playing from position: {self.position:.2f}s")
            return True
            
        except Exception as e:
            print(f"Error playing audio: {e}")
            return False
    
    def pause(self):
        """Pause audio playback"""
        if self.is_playing and not self.is_paused:
            # Update position before pausing
            current_pos = time.time() - self.start_time
            self.position = min(current_pos, self.audio_length)
            
            # Stop the current playback
            sd.stop()
            self.stop_event.set()
            
            self.is_paused = True
            print(f"Paused at position: {self.position:.2f}s")
    
    def unpause(self):
        """Resume audio playback"""
        if self.is_paused:
            self.is_paused = False
            self.play(self.position)
            print(f"Resumed from position: {self.position:.2f}s")
    
    def stop(self):
        """Stop audio playback"""
        if self.is_playing or self.is_paused:
            # Stop sounddevice playback
            sd.stop()
            self.stop_event.set()
            
            # Wait for playback thread to finish
            if self.playback_thread and self.playback_thread.is_alive():
                self.playback_thread.join(timeout=1.0)
            
            self.is_playing = False
            self.is_paused = False
            self.position = 0
            print("Stopped playback")
    
    def seek(self, position):
        """Seek to a specific position in seconds"""
        old_position = self.position
        self.position = max(0, min(position, self.audio_length))
        
        # If currently playing, restart from new position
        if self.is_playing and not self.is_paused:
            self.play(self.position)
        
        print(f"Seeked from {old_position:.2f}s to {self.position:.2f}s")
    
    def get_position(self):
        """Get current playback position in seconds"""
        if self.is_playing and not self.is_paused:
            current_pos = time.time() - self.start_time
            self.position = min(current_pos, self.audio_length)
            
            # Check if playback has finished
            if self.position >= self.audio_length:
                self.is_playing = False
                self.is_paused = False
                
        return self.position
    
    def get_length(self):
        """Get total audio length in seconds"""
        return self.audio_length

class ProjectLoader:
    """Handles loading and parsing karaoke project folders"""
    
    @staticmethod
    def find_audio_file(project_dir):
        """Find the main audio file in project directory"""
        audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.aac')
        project_path = Path(project_dir)
        
        # Look for files named song first
        for file in project_path.iterdir():
            if file.name.lower() == 'song':
                return str(file)

        # Look for common audio files
        for file in project_path.iterdir():
            if file.suffix.lower() in audio_extensions:
                return str(file)
        return None
    
    @staticmethod
    def find_alignment_file(project_dir):
        """Find the alignment JSON file in project directory"""
        project_path = Path(project_dir)
        
        # First look for project file
        for file in project_path.iterdir():
            if file.suffix.lower() == '.json' and 'project' in file.name:
                return str(file)
                
        # Then look for alignment file
        for file in project_path.iterdir():
            if file.suffix.lower() == '.json' and 'lyrics_alignment' in file.name:
                return str(file)
        return None
    
    @staticmethod
    def load_alignment_data(alignment_file):
        """Load and parse alignment JSON data"""
        try:
            with open(alignment_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Convert data to standard format
            words = []
            
            # Format 1: Direct list of word objects (current format)
            if isinstance(data, list):
                words = data
            # Format 2: Segments with words
            elif isinstance(data, dict) and 'segments' in data:
                for segment in data['segments']:
                    if 'words' in segment:
                        words.extend(segment['words'])
            # Format 3: Direct words in dict
            elif isinstance(data, dict) and 'words' in data:
                words = data['words']
            
            # Convert to standard format
            standardized_words = []
            for i, word in enumerate(words):
                standardized_word = {
                    'text': word.get('word', word.get('text', '')),
                    'index': i,
                    'begin': word.get('start', word.get('begin', 0)),
                    'end': word.get('end', word.get('end', 0))
                }
                # Add line_end if available
                if 'line_end' in word:
                    standardized_word['line_end'] = word['line_end']
                standardized_words.append(standardized_word)
                
            return standardized_words
            
        except Exception as e:
            print(f"Error loading alignment file: {e}")
            return None
            
    @staticmethod
    def save_project_data(project_dir, word_data):
        """Save project data to a JSON file"""
        try:
            project_path = Path(project_dir)
            project_file = project_path / "metadata.json"
            
            with open(project_file, 'w', encoding='utf-8') as f:
                json.dump(word_data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving project file: {e}")
            return False

class WordDetailsEditor(QWidget):
    """Widget for editing word details and timings"""
    
    word_changed = pyqtSignal(object, str)  # Emitted when word is changed (word_data, source)
    
    def __init__(self):
        super().__init__()
        self.current_word = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Word Details")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Word text display
        word_layout = QHBoxLayout()
        word_layout.addWidget(QLabel("Word:"))
        self.word_edit = QTextEdit()
        self.word_edit.setFixedHeight(35)  
        self.word_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.word_edit.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.word_edit.setStyleSheet("""
            QTextEdit {
                color: #2E8B57;
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QTextEdit:focus {
                border: 1px solid #2E8B57;
            }
        """)
        self.word_edit.textChanged.connect(self.on_word_text_changed)
        word_layout.addWidget(self.word_edit)
        word_layout.addStretch()
        layout.addLayout(word_layout)
        
        # Timing controls
        timing_frame = QFrame()
        timing_frame.setFrameStyle(QFrame.Shape.Box)
        timing_frame.setStyleSheet("QFrame { border: 1px solid #ccc; border-radius: 5px; padding: 3px; }")
        timing_layout = QVBoxLayout()
        
        # Start time
        start_layout = QHBoxLayout()
        start_layout.addWidget(QLabel("Start Time (seconds):"))
        self.start_spinbox = QDoubleSpinBox()
        self.start_spinbox.setDecimals(3)
        self.start_spinbox.setRange(0.0, 999999.0)
        self.start_spinbox.setSingleStep(0.1)
        self.start_spinbox.valueChanged.connect(self.on_timing_changed)
        start_layout.addWidget(self.start_spinbox)
        timing_layout.addLayout(start_layout)
        
        # End time
        end_layout = QHBoxLayout()
        end_layout.addWidget(QLabel("End Time (seconds):"))
        self.end_spinbox = QDoubleSpinBox()
        self.end_spinbox.setDecimals(3)
        self.end_spinbox.setRange(0.0, 999999.0)
        self.end_spinbox.setSingleStep(0.1)
        self.end_spinbox.valueChanged.connect(self.on_timing_changed)
        end_layout.addWidget(self.end_spinbox)
        timing_layout.addLayout(end_layout)
        
        # Duration display and line end toggle in same row
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Duration:"))
        self.duration_label = QLabel("0.000s")
        self.duration_label.setStyleSheet("font-weight: bold; color: #4682B4;")
        duration_layout.addWidget(self.duration_label)
        
        # Add line end checkbox to the same row
        self.line_end_checkbox = QCheckBox("Line End")
        self.line_end_checkbox.stateChanged.connect(self.on_line_end_changed)
        duration_layout.addWidget(self.line_end_checkbox)
        
        duration_layout.addStretch()
        timing_layout.addLayout(duration_layout)
        
        timing_frame.setLayout(timing_layout)
        layout.addWidget(timing_frame)
        
        # Quick adjustment buttons
        adjust_frame = QFrame()
        adjust_frame.setFrameStyle(QFrame.Shape.Box)
        adjust_frame.setStyleSheet("QFrame { border: 1px solid #ccc; border-radius: 5px; padding: 5px; }")
        adjust_layout = QVBoxLayout()
        
        adjust_title = QLabel("Quick Adjustments")
        adjust_title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        adjust_layout.addWidget(adjust_title)
        
        # Time adjustment buttons
        button_layout1 = QHBoxLayout()
        
        self.start_minus_btn = QPushButton("-0.1s")
        self.start_minus_btn.clicked.connect(lambda: self.adjust_start(-0.1))
        button_layout1.addWidget(self.start_minus_btn)
        
        self.start_plus_btn = QPushButton("+0.1s")
        self.start_plus_btn.clicked.connect(lambda: self.adjust_start(0.1))
        button_layout1.addWidget(self.start_plus_btn)
        
        button_layout1.addWidget(QLabel("Start"))
        
        adjust_layout.addLayout(button_layout1)
        
        button_layout2 = QHBoxLayout()
        
        self.end_minus_btn = QPushButton("-0.1s")
        self.end_minus_btn.clicked.connect(lambda: self.adjust_end(-0.1))
        button_layout2.addWidget(self.end_minus_btn)
        
        self.end_plus_btn = QPushButton("+0.1s")
        self.end_plus_btn.clicked.connect(lambda: self.adjust_end(0.1))
        button_layout2.addWidget(self.end_plus_btn)
        
        button_layout2.addWidget(QLabel("End"))
        
        adjust_layout.addLayout(button_layout2)
        
        adjust_frame.setLayout(adjust_layout)
        layout.addWidget(adjust_frame)
        
        # Spacer to push everything to top
        layout.addStretch()
        
        self.setLayout(layout)
        self.setEnabled(False)  # Disabled until a word is selected
        
    def set_word(self, word_data):
        """Set the current word data for editing"""
        self.current_word = word_data
        
        if word_data is None:
            self.word_edit.setText("")
            self.start_spinbox.setValue(0.0)
            self.end_spinbox.setValue(0.0)
            self.duration_label.setText("0.000s")
            self.line_end_checkbox.setChecked(False)
            self.setEnabled(False)
        else:
            # Handle different field names
            word_text = word_data.get('word', word_data.get('text', ''))
            start_time = word_data.get('start', word_data.get('begin', 0))
            end_time = word_data.get('end', word_data.get('end', 0))
            line_end = word_data.get('line_end', False)
            
            # Temporarily disconnect signals to avoid triggering changes
            self.word_edit.textChanged.disconnect()
            self.start_spinbox.valueChanged.disconnect()
            self.end_spinbox.valueChanged.disconnect()
            self.line_end_checkbox.stateChanged.disconnect()
            
            self.word_edit.setText(word_text)
            self.start_spinbox.setValue(start_time)
            self.end_spinbox.setValue(end_time)
            self.line_end_checkbox.setChecked(line_end)
            
            # Reconnect signals
            self.word_edit.textChanged.connect(self.on_word_text_changed)
            self.start_spinbox.valueChanged.connect(self.on_timing_changed)
            self.end_spinbox.valueChanged.connect(self.on_timing_changed)
            self.line_end_checkbox.stateChanged.connect(self.on_line_end_changed)
            
            self.update_duration()
            self.setEnabled(True)
    
    def update_duration(self):
        """Update the duration display"""
        duration = self.end_spinbox.value() - self.start_spinbox.value()
        self.duration_label.setText(f"{duration:.3f}s")
    
    def on_word_text_changed(self):
        """Handle word text changes"""
        if self.current_word is not None:
            # Create updated word data
            updated_word = self.current_word.copy()
            
            # Update text field (handle different field names)
            new_text = self.word_edit.toPlainText().strip()
            if 'word' in updated_word:
                updated_word['word'] = new_text
            elif 'text' in updated_word:
                updated_word['text'] = new_text
            
            # Update current word data
            self.current_word = updated_word
            
            # Emit change signal with source
            self.word_changed.emit(updated_word, 'details')
    
    def on_timing_changed(self):
        """Handle timing changes from spinboxes"""
        if self.current_word is not None:
            # Ensure end time is always greater than start time
            if self.end_spinbox.value() <= self.start_spinbox.value():
                self.end_spinbox.setValue(self.start_spinbox.value() + 0.05)
            
            self.update_duration()
            
            # Create updated word data
            updated_word = self.current_word.copy()
            
            # Update timing fields (handle different field names)
            if 'start' in updated_word:
                updated_word['start'] = self.start_spinbox.value()
            elif 'begin' in updated_word:
                updated_word['begin'] = self.start_spinbox.value()
                
            if 'end' in updated_word:
                updated_word['end'] = self.end_spinbox.value()
            
            # Update current word data
            self.current_word = updated_word
            
            # Emit change signal with source
            self.word_changed.emit(updated_word, 'details')
    
    def adjust_start(self, delta):
        """Adjust start time by delta seconds"""
        new_value = max(0.0, self.start_spinbox.value() + delta)
        self.start_spinbox.setValue(new_value)
    
    def adjust_end(self, delta):
        """Adjust end time by delta seconds"""
        self.end_spinbox.setValue(self.end_spinbox.value() + delta)
    
    def on_line_end_changed(self, state):
        """Handle line end checkbox state change"""
        if self.current_word is not None:
            # Create updated word data
            updated_word = self.current_word.copy()
            updated_word['line_end'] = state == Qt.CheckState.Checked.value
            
            # Update current word data
            self.current_word = updated_word
            
            # Emit change signal with source
            self.word_changed.emit(updated_word, 'details')

class WordTimingWidget(QWidget):
    """Widget for displaying and editing word timings"""
    
    word_selected = pyqtSignal(object)  # Signal when a word is selected in the list
    word_centered = pyqtSignal(float)  # Signal to center timeline on word
    
    def __init__(self):
        super().__init__()
        self.alignment_data = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Word Timings")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Word list
        self.word_list = QListWidget()
        self.word_list.itemClicked.connect(self.on_word_selected)
        layout.addWidget(self.word_list)
        
        self.setLayout(layout)
        
    def load_alignment_data(self, alignment_data):
        """Load alignment data and populate word list"""
        self.alignment_data = alignment_data
        self.word_list.clear()
        
        if not alignment_data:
            return
            
        # Handle different alignment data formats
        words = []
        
        # Format 1: Direct list of word objects (current format)
        if isinstance(alignment_data, list):
            words = alignment_data
        # Format 2: Segments with words
        elif isinstance(alignment_data, dict) and 'segments' in alignment_data:
            for segment in alignment_data['segments']:
                if 'words' in segment:
                    words.extend(segment['words'])
        # Format 3: Direct words in dict
        elif isinstance(alignment_data, dict) and 'words' in alignment_data:
            words = alignment_data['words']
            
        # Populate list
        for i, word_data in enumerate(words):
            # Handle different field names
            word = word_data.get('word', word_data.get('text', '')).strip()
            start = word_data.get('start', word_data.get('begin', 0))
            end = word_data.get('end', word_data.get('end', 0))
            
            item_text = f"{word} ({start:.2f}s - {end:.2f}s)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, word_data)
            self.word_list.addItem(item)
            
    def on_word_selected(self, item):
        """Handle word selection"""
        word_data = item.data(Qt.ItemDataRole.UserRole)
        if word_data:
            # Calculate center position of the word
            start = word_data.get('start', word_data.get('begin', 0))
            end = word_data.get('end', word_data.get('end', 0))
            center = (start + end) / 2
            
            # Emit signals
            self.word_selected.emit(word_data)
            self.word_centered.emit(center)
            
    def update_word_timing(self, word_data):
        """Update word timing in the list"""
        if not word_data:
            return
            
        # Find the word in the list
        for i in range(self.word_list.count()):
            item = self.word_list.item(i)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            
            # Match by text and index
            if (item_data.get('index', -1) == word_data.get('index', -2)):
                
                # Update the item text
                word = word_data.get('word', word_data.get('text', '')).strip()
                start = word_data.get('start', word_data.get('begin', 0))
                end = word_data.get('end', word_data.get('end', 0))
                item_text = f"{word} ({start:.2f}s - {end:.2f}s)"
                item.setText(item_text)
                
                # Update the item data
                item.setData(Qt.ItemDataRole.UserRole, word_data)
                break
                
    def select_word(self, word_data):
        """Select a word in the list"""
        if not word_data:
            return
            
        # Find the word in the list
        for i in range(self.word_list.count()):
            item = self.word_list.item(i)
            item_data = item.data(Qt.ItemDataRole.UserRole)
            
            # Match by text and index
            if (item_data.get('word', item_data.get('text', '')) == word_data.get('word', word_data.get('text', '')) and
                item_data.get('index', -1) == word_data.get('index', -1)):
                
                # Select the item
                self.word_list.setCurrentItem(item)
                self.word_list.scrollToItem(item)
                break

class WordOperationsWidget(QWidget):
    """Widget for word manipulation operations"""
    
    word_added = pyqtSignal(object)  # Emitted when a new word is added
    word_duplicated = pyqtSignal(object)  # Emitted when a word is duplicated
    word_deleted = pyqtSignal(object)  # Emitted when a word is deleted
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_word = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Word Operations")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        layout.addWidget(title)
        
        # Operations frame
        operations_frame = QFrame()
        operations_frame.setFrameStyle(QFrame.Shape.Box)
        operations_frame.setStyleSheet("QFrame { border: 1px solid #ccc; border-radius: 5px; padding: 10px; }")
        operations_layout = QVBoxLayout()
        
        # Add new word button
        self.add_word_btn = QPushButton("Add New Word")
        self.add_word_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.add_word_btn.clicked.connect(self.add_new_word)
        operations_layout.addWidget(self.add_word_btn)
        
        # Duplicate word button
        self.duplicate_word_btn = QPushButton("Duplicate Word")
        self.duplicate_word_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        self.duplicate_word_btn.clicked.connect(self.duplicate_word)
        operations_layout.addWidget(self.duplicate_word_btn)
        
        # Delete word button
        self.delete_word_btn = QPushButton("Delete Word")
        self.delete_word_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
        """)
        self.delete_word_btn.clicked.connect(self.delete_word)
        operations_layout.addWidget(self.delete_word_btn)
        
        operations_frame.setLayout(operations_layout)
        layout.addWidget(operations_frame)
        
        # Spacer to push everything to top
        layout.addStretch()
        
        self.setLayout(layout)
        self.setEnabled(False)  # Disabled until a word is selected
        
    def set_word(self, word_data):
        """Set the current word data"""
        self.current_word = word_data
        self.setEnabled(word_data is not None)
        
    def add_new_word(self):
        """Add a new word at the current playhead position"""
        # Get the main window instance
        main_window = self.window()
        if not isinstance(main_window, KaraokeEditorMainWindow):
            return
            
        # Get current playhead position from the timeline
        current_pos = main_window.audio_timeline.get_position()
        
        # Create new word data
        new_word = {
            'text': 'new',
            'begin': current_pos,
            'end': current_pos + 0.25,  # 0.25 seconds duration
            'line_end': False
        }
        
        self.word_added.emit(new_word)
        
    def duplicate_word(self):
        """Duplicate the current word"""
        if not self.current_word:
            return
            
        # Create a copy of the current word
        new_word = self.current_word.copy()
        
        main_window = self.window()
        if not isinstance(main_window, KaraokeEditorMainWindow):
            return
            
        # Get current playhead position from the timeline
        current_pos = main_window.audio_timeline.get_position()

        # Assign new word to play head
        new_word['begin'] = current_pos
        new_word['end'] = current_pos + self.current_word['end'] - self.current_word['begin'] 

        # Emit the signal with the new word data
        self.word_duplicated.emit(new_word)
        
    def delete_word(self):
        """Delete the current word"""
        if not self.current_word:
            return
            
        self.word_deleted.emit(self.current_word)

class ProcessThread(QThread):
    """Thread for running the karaoke processing steps"""
    progress = pyqtSignal(str)  # Progress message
    finished = pyqtSignal(dict)  # Results dictionary
    error = pyqtSignal(str)  # Error message
    
    def __init__(self, input_dir, output_dir):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        
    def run(self):
        try:
            from signal_based_processors import run_process_mode_with_signals
            
            # Run the process with progress signals
            results = run_process_mode_with_signals(self.input_dir, self.output_dir, self.progress)
            if results:
                self.finished.emit(results)
            else:
                self.error.emit("Processing failed")
                
        except Exception as e:
            self.error.emit(str(e))

class VideoExportThread(QThread):
    """Thread for generating the karaoke video"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, instrumental_path, alignment_path, output_name, output_dir, resolution="1280x720", use_wipe=True, song_title=None, artist=None):
        super().__init__()
        self.instrumental_path = instrumental_path
        self.alignment_path = alignment_path
        self.output_name = output_name
        self.output_dir = output_dir
        self.resolution = resolution
        self.use_wipe = use_wipe
        self.song_title = song_title
        self.artist = artist
        
    def run(self):
        try:
            from generate_video_in_process import generate_video_in_process
            
            # Generate video in separate process
            result = generate_video_in_process(
                self.instrumental_path,
                self.alignment_path,
                self.output_name,
                self.output_dir,
                self.resolution,
                self.use_wipe,
                progress_callback=self.progress.emit,
                song_title=self.song_title,
                artist=self.artist
            )
            
            if result:
                self.finished.emit(result)
            else:
                self.error.emit("Video generation failed")
                
        except Exception as e:
            self.error.emit(str(e))

class KaraokeEditorMainWindow(QMainWindow):
    """Main window for the karaoke timing editor"""
    
    def __init__(self):
        super().__init__()
        self.audio_player = AudioPlayer()
        self.current_project_dir = None
        self.project_metadata = {
            'name': '',
            'artist': '',
            'audio_file': '',
            'lyrics_file': ''
        }
        self.process_thread = None
        self.export_thread = None
        self.setup_ui()
        
    def setup_ui(self):
        self.setWindowTitle("Karaoke Timing Editor")
        self.setGeometry(100, 100, 1200, 800)
        
        # Enable keyboard focus and events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Menu bar
        self.setup_menu_bar()
        
        # Project info
        project_layout = QHBoxLayout()
        self.project_label = QLabel("No project loaded")
        self.project_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        project_layout.addWidget(self.project_label)
        
        new_project_button = QPushButton("New Project")
        new_project_button.clicked.connect(self.create_new_project)
        project_layout.addWidget(new_project_button)
        
        edit_project_button = QPushButton("Edit Project Properties")
        edit_project_button.clicked.connect(self.edit_project)
        project_layout.addWidget(edit_project_button)
        
        open_button = QPushButton("Load Project From Folder")
        open_button.clicked.connect(self.open_project_folder)
        project_layout.addWidget(open_button)
        
        save_button = QPushButton("Save Project")
        save_button.clicked.connect(self.save_project)
        project_layout.addWidget(save_button)
        
        # Add process and export buttons
        process_button = QPushButton("Process Project")
        process_button.clicked.connect(self.process_project)
        project_layout.addWidget(process_button)
        
        export_button = QPushButton("Export Video")
        export_button.clicked.connect(self.export_video)
        project_layout.addWidget(export_button)
        
        project_layout.addStretch()
        main_layout.addLayout(project_layout)
        
        # Splitter for main content
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Word timing widget
        self.word_timing_widget = WordTimingWidget()
        self.word_timing_widget.word_selected.connect(self.on_word_selected)
        self.word_timing_widget.word_centered.connect(self.center_timeline_on_word)
        splitter.addWidget(self.word_timing_widget)
        
        # Right panel - Word details editor and operations
        right_panel = QWidget()
        right_layout = QHBoxLayout()
        right_panel.setLayout(right_layout)
        
        # Word details editor
        self.word_details_editor = WordDetailsEditor()
        self.word_details_editor.word_changed.connect(self.on_word_changed)
        right_layout.addWidget(self.word_details_editor)
        
        # Word operations widget
        self.word_operations = WordOperationsWidget(self)
        self.word_operations.word_added.connect(self.add_word)
        self.word_operations.word_duplicated.connect(self.add_word)
        self.word_operations.word_deleted.connect(self.delete_word)
        right_layout.addWidget(self.word_operations)
        
        splitter.addWidget(right_panel)
        
        # Set splitter proportions
        splitter.setSizes([400, 800])
        
        # Audio timeline at bottom
        self.audio_timeline = AudioTimelineWidget()
        self.audio_timeline.position_changed.connect(self.on_timeline_seek)
        self.audio_timeline.word_selected.connect(self.on_word_selected)
        self.audio_timeline.word_changed.connect(lambda word: self.on_word_changed(word, 'timeline'))
        self.word_details_editor.word_changed.connect(self.on_word_changed)
        main_layout.addWidget(self.audio_timeline)
        
        # Simple audio controls
        controls_layout = QHBoxLayout()
        
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.play_button)
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_audio)
        controls_layout.addWidget(self.stop_button)
        
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)
        
        # Timer for updating timeline position
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self.update_timeline_position)
        self.position_timer.start(100)  # Update every 100ms
        
        # Status bar
        self.statusBar().showMessage("Ready - Open a project folder to begin")
        
    def setup_menu_bar(self):
        """Setup the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu('File')
        
        new_project_action = file_menu.addAction('New Project')
        new_project_action.triggered.connect(self.create_new_project)
        new_project_action.setShortcut(QKeySequence.StandardKey.New)
        
        edit_project_action = file_menu.addAction('Edit Project')
        edit_project_action.triggered.connect(self.edit_project)
        
        open_action = file_menu.addAction('Open Project Folder')
        open_action.triggered.connect(self.open_project_folder)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        
        save_action = file_menu.addAction('Save Project')
        save_action.triggered.connect(self.save_project)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction('Exit')
        exit_action.triggered.connect(self.close)
        
    def open_project_folder(self):
        """Open and load a project folder"""
        folder = QFileDialog.getExistingDirectory(
            self, 
            "Select Project Folder",
            str(Path.home())
        )
        
        if folder:
            self.load_project(folder)
            
    def load_project(self, project_dir):
        """Load a karaoke project from directory"""
        self.current_project_dir = project_dir
        project_path = Path(project_dir)
        
        # Load metadata if it exists
        metadata_file = project_path / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    self.project_metadata = json.load(f)
            except Exception as e:
                print(f"Error loading metadata: {e}")
                self.project_metadata = {
                    'name': '',
                    'artist': '',
                    'audio_file': '',
                    'lyrics_file': ''
                }
        
        # Update project label with metadata if available
        if self.project_metadata['name']:
            display_name = self.project_metadata['name']
            if self.project_metadata['artist']:
                display_name = f"{self.project_metadata['artist']} - {display_name}"
            self.project_label.setText(f"Project: {display_name}")
        else:
            self.project_label.setText(f"Project: {project_path.name}")
        
        # Find and load audio file
        audio_file = ProjectLoader.find_audio_file(project_dir)
        if audio_file:
            if self.audio_player.load_audio(audio_file):
                # Set audio length in timeline
                audio_length = self.audio_player.get_length()
                self.audio_timeline.set_audio_length(audio_length)
                self.statusBar().showMessage(f"Loaded audio: {Path(audio_file).name}")
            else:
                self.statusBar().showMessage("Error loading audio file")
        else:
            self.statusBar().showMessage("No audio file found in project")
            
        # Find and load alignment data
        alignment_file = ProjectLoader.find_alignment_file(project_dir)
        if alignment_file:
            alignment_data = ProjectLoader.load_alignment_data(alignment_file)
            if alignment_data:
                self.word_timing_widget.load_alignment_data(alignment_data)
                
                # Extract word timings for timeline display
                word_timings = []
                if isinstance(alignment_data, list):
                    word_timings = alignment_data
                elif isinstance(alignment_data, dict) and 'segments' in alignment_data:
                    for segment in alignment_data['segments']:
                        if 'words' in segment:
                            word_timings.extend(segment['words'])
                elif isinstance(alignment_data, dict) and 'words' in alignment_data:
                    word_timings = alignment_data['words']
                
                # Set word timings in timeline
                self.audio_timeline.set_word_timings(word_timings)
                
                self.statusBar().showMessage(f"Loaded alignment data: {Path(alignment_file).name}")
            else:
                self.statusBar().showMessage("Error loading alignment file")
        else:
            self.statusBar().showMessage("No alignment file found in project")
            
    def toggle_play(self):
        """Toggle play/pause - starts from current playhead position"""
        if self.audio_player.is_playing:
            if self.audio_player.is_paused:
                # Resume from current timeline position
                playhead_position = self.audio_timeline.get_position()
                self.audio_player.play(playhead_position)
                self.play_button.setText("Pause")
            else:
                self.audio_player.pause()
                self.play_button.setText("Play")
        else:
            # Get current playhead position from timeline
            playhead_position = self.audio_timeline.get_position()
            self.audio_player.play(playhead_position)
            self.play_button.setText("Pause")
            
    def stop_audio(self):
        """Stop audio playback"""
        self.audio_player.stop()
        # Reset timeline position to beginning when stopping
        self.audio_timeline.set_position(0)
        self.play_button.setText("Play")
        
    def on_timeline_seek(self, position):
        """Handle seeking from timeline"""
        self.audio_player.seek(position)
        # Also update the timeline position to reflect the seek
        self.audio_timeline.set_position(position)
        
    def update_timeline_position(self):
        """Update timeline with current playback position"""
        if self.audio_player.audio_file:
            # Only update timeline position when actively playing
            if self.audio_player.is_playing and not self.audio_player.is_paused:
                current_pos = self.audio_player.get_position()
                self.audio_timeline.set_position(current_pos)
                self.play_button.setText("Pause")
            else:
                # When paused or stopped, don't update timeline position
                # This preserves the playhead position for resume
                self.play_button.setText("Play")
    
    def on_timeline_word_selected(self, word_data):
        """Handle word selection from timeline"""
        self.on_word_selected(word_data)
        
    def on_word_changed(self, word_data, source):
        """Handle word changes from any source"""
        # Update the timeline display
        if hasattr(self.audio_timeline, 'selected_word_index') and \
           self.audio_timeline.selected_word_index >= 0 and \
           source != 'timeline':
            # Update the word in the timeline's data
            index = self.audio_timeline.selected_word_index
            if 0 <= index < len(self.audio_timeline.word_timings):
                self.audio_timeline.word_timings[index] = word_data
                self.audio_timeline.update()  # Trigger redraw

        # Update the word details editor display if change came from timeline
        if source != 'details' and hasattr(self.word_details_editor, 'current_word'):
            self.word_details_editor.set_word(word_data)
                
        # Update word list
        self.word_timing_widget.update_word_timing(word_data)
        
    def on_word_selected(self, word_data):
        """Handle word selection from any source"""
        if word_data:
            # Update word details editor
            self.word_details_editor.set_word(word_data)
            # Update word operations
            self.word_operations.set_word(word_data)
            # Select word in list
            self.word_timing_widget.select_word(word_data)
            
            # Find and select the word in the timeline
            for i, word in enumerate(self.audio_timeline.word_timings):
                if (word.get('index', -1) == word_data.get('index', -2)):
                    self.audio_timeline.set_selected_word(i)
                    break

    def closeEvent(self, event):
        """Handle application close"""
        self.audio_player.stop()
        event.accept()

    def keyPressEvent(self, event):
        """Handle keyboard events"""
        if event.key() == Qt.Key.Key_Space:
            # Spacebar triggers play/pause
            self.toggle_play()
            event.accept()
        elif event.key() == Qt.Key.Key_S and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Ctrl+S triggers save
            self.save_project()
            event.accept()
        else:
            # Pass other key events to parent
            super().keyPressEvent(event)

    def save_project(self):
        """Save the current project data"""
        if not self.current_project_dir:
            self.statusBar().showMessage("No project loaded to save")
            return
            
        # Get word data from timeline
        word_data = self.audio_timeline.word_timings
        
        # Save both word data and metadata
        try:
            project_path = Path(self.current_project_dir)
            
            # Save word data
            with open(project_path / "project.json", 'w', encoding='utf-8') as f:
                json.dump(word_data, f, indent=2)
                
            # Save metadata
            with open(project_path / "metadata.json", 'w', encoding='utf-8') as f:
                json.dump(self.project_metadata, f, indent=2)
                
            self.statusBar().showMessage("Project saved successfully")
        except Exception as e:
            self.statusBar().showMessage(f"Error saving project: {e}")

    def add_word(self, word_data):
        """Add a new word to the timeline"""
        # Find the correct index to insert the word
        insert_index = 0
        for i, word in enumerate(self.audio_timeline.word_timings):
            if word.get('begin', 0) > word_data['begin']:
                break
            insert_index = i + 1
            
        # Create a copy of the word data to avoid reference issues
        new_word = {
            'text': word_data['text'],
            'begin': word_data['begin'],
            'end': word_data['end'],
            'line_end': word_data.get('line_end', False),
            'index': insert_index  # Set initial index
        }
            
        # Insert the word
        self.audio_timeline.word_timings.insert(insert_index, new_word)
        
        # Update all indexes
        self.update_word_indexes()
        
        # Update displays
        self.audio_timeline.update()
        self.word_timing_widget.load_alignment_data(self.audio_timeline.word_timings)
        
        # Select the new word
        self.audio_timeline.set_selected_word(insert_index)
        
    def delete_word(self, word_data):
        """Delete a word from the timeline"""
        # Find the index of the word to delete
        delete_index = -1
        for i, word in enumerate(self.audio_timeline.word_timings):
            if (word.get('text', '') == word_data.get('text', '') and
                word.get('begin', 0) == word_data.get('begin', 0)):
                delete_index = i
                break
                
        if delete_index >= 0:
            # Remove the word
            self.audio_timeline.word_timings.pop(delete_index)
            
            # Update all indexes
            self.update_word_indexes()
            
            # Update displays
            self.audio_timeline.update()
            self.word_timing_widget.load_alignment_data(self.audio_timeline.word_timings)
            
            # Clear selection
            self.audio_timeline.set_selected_word(-1)
            self.word_details_editor.set_word(None)
            self.word_operations.set_word(None)
            
    def update_word_indexes(self):
        """Update the index field for all words"""
        for i, word in enumerate(self.audio_timeline.word_timings):
            word['index'] = i

    def center_timeline_on_word(self, center_position):
        """Center the timeline view on a specific word"""
        # Calculate new scroll position to center the word
        visible_duration = self.audio_timeline.zoom_level
        new_scroll = max(0, center_position - (visible_duration / 2))
        
        # Update timeline scroll position
        self.audio_timeline.scroll_position = new_scroll
        self.audio_timeline.update_scroll_bar_position()
        self.audio_timeline.update()
        
        # Also seek to this position
        self.audio_player.seek(center_position)

    def create_new_project(self):
        """Create a new project"""
        dialog = ProjectPropertiesDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            project_data = dialog.get_project_data()
            
            # Validate required fields
            if not all([project_data['name'], project_data['audio_file'], project_data['lyrics_file']]):
                self.statusBar().showMessage("Error: Song name, audio file, and lyrics file are required")
                return
                
            # Create project directory
            project_dir = Path("songs") / project_data['name']
            project_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy files to project directory
            audio_ext = Path(project_data['audio_file']).suffix
            shutil.copy2(project_data['audio_file'], project_dir / f"song{audio_ext}")
            shutil.copy2(project_data['lyrics_file'], project_dir / "lyrics.txt")
            
            # Update metadata
            self.project_metadata = {
                'name': project_data['name'],
                'artist': project_data['artist'],
                'audio_file': str(project_dir / f"song{audio_ext}"),
                'lyrics_file': str(project_dir / "lyrics.txt")
            }
            
            # Save metadata
            with open(project_dir / "metadata.json", 'w', encoding='utf-8') as f:
                json.dump(self.project_metadata, f, indent=2)
                
            # Load the new project
            self.load_project(str(project_dir))
            self.statusBar().showMessage(f"Created new project: {project_data['name']}")
            
    def edit_project(self):
        """Edit current project properties"""
        if not self.current_project_dir:
            self.statusBar().showMessage("No project loaded to edit")
            return
            
        # Show edit dialog with current metadata
        dialog = ProjectPropertiesDialog(self, self.project_metadata)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_project_data()
            
            # Validate required fields
            if not all([new_data['name'], new_data['audio_file'], new_data['lyrics_file']]):
                self.statusBar().showMessage("Error: Song name, audio file, and lyrics file are required")
                return
                
            # Update project directory if name changed
            if new_data['name'] != self.project_metadata['name']:
                new_dir = Path("songs") / new_data['name']
                if new_dir.exists():
                    self.statusBar().showMessage("Error: A project with this name already exists")
                    return
                    
                # Rename directory
                old_dir = Path(self.current_project_dir)
                old_dir.rename(new_dir)
                self.current_project_dir = str(new_dir)
                
            # Copy new files if they changed
            if new_data['audio_file'] != self.project_metadata['audio_file']:
                audio_ext = Path(new_data['audio_file']).suffix
                shutil.copy2(new_data['audio_file'], Path(self.current_project_dir) / f"song{audio_ext}")
                new_data['audio_file'] = str(Path(self.current_project_dir) / f"song{audio_ext}")
                
            if new_data['lyrics_file'] != self.project_metadata['lyrics_file']:
                shutil.copy2(new_data['lyrics_file'], Path(self.current_project_dir) / "lyrics.txt")
                new_data['lyrics_file'] = str(Path(self.current_project_dir) / "lyrics.txt")
                
            # Update metadata
            self.project_metadata = new_data
                
            # Save metadata
            with open(Path(self.current_project_dir) / "metadata.json", 'w', encoding='utf-8') as f:
                json.dump(self.project_metadata, f, indent=2)
                
            # Reload project
            self.load_project(self.current_project_dir)
            self.statusBar().showMessage("Project updated successfully")

    def process_project(self):
        """Run the processing steps (separation and alignment) in background"""
        if not self.current_project_dir:
            self.statusBar().showMessage("No project loaded to process")
            return
            
        # Disable process button while running
        for button in self.findChildren(QPushButton):
            if button.text() == "Process Project":
                button.setEnabled(False)
                break
                
        # Create and start processing thread
        self.process_thread = ProcessThread(self.current_project_dir, self.current_project_dir)
        self.process_thread.progress.connect(self.statusBar().showMessage)
        self.process_thread.finished.connect(self.on_processing_finished)
        self.process_thread.error.connect(self.on_processing_error)
        self.process_thread.start()
        
    def on_processing_finished(self, results):
        """Handle successful completion of processing"""
        # Re-enable process button
        for button in self.findChildren(QPushButton):
            if button.text() == "Process Project":
                button.setEnabled(True)
                break
                
        self.statusBar().showMessage("Project processed successfully")

    def on_processing_finished(self, results):
        """Handle successful completion of processing"""
        # Re-enable process button
        for button in self.findChildren(QPushButton):
            if button.text() == "Process Project":
                button.setEnabled(True)
                break
                
        # Delete project.json if it exists
        project_json = Path(self.current_project_dir) / "project.json"
        if project_json.exists():
            project_json.unlink()

        # Reload the project to show new alignment data
        self.load_project(self.current_project_dir)
        
    def on_processing_error(self, error_msg):
        """Handle processing error"""
        # Re-enable process button
        for button in self.findChildren(QPushButton):
            if button.text() == "Process Project":
                button.setEnabled(True)
                break
                
        self.statusBar().showMessage(f"Error: {error_msg}")
            
    def export_video(self):
        """Generate the karaoke video in background"""
        if not self.current_project_dir:
            self.statusBar().showMessage("No project loaded to export")
            return
            
        # Find the instrumental and alignment files
        project_path = Path(self.current_project_dir)
        instrumental_path = None
        alignment_path = None
        
        # Look for instrumental file
        for file in project_path.iterdir():
            if file.name.startswith('song_instrumental'):
                instrumental_path = str(file)
                break
                
        # Look for alignment file
        for file in project_path.iterdir():
            if file.name.endswith('project.json'):
                alignment_path = str(file)
                break
            if file.name.endswith('lyrics_alignment.json'):
                alignment_path = str(file)
                
        if not instrumental_path or not alignment_path:
            self.statusBar().showMessage("Error: Could not find required files for video generation")
            return
            
        # Disable export button while running
        for button in self.findChildren(QPushButton):
            if button.text() == "Export Video":
                button.setEnabled(False)
                break
                
        # Get output name and metadata
        output_name = self.project_metadata['name'] if self.project_metadata['name'] else project_path.name
        song_title = self.project_metadata.get('name', '')
        artist = self.project_metadata.get('artist', '')
        
        # Create and start export thread
        self.export_thread = VideoExportThread(
            instrumental_path,
            alignment_path,
            output_name,
            str(project_path),
            resolution="360",
            use_wipe=True,
            song_title=song_title,
            artist=artist
        )
        self.export_thread.progress.connect(self.statusBar().showMessage)
        self.export_thread.finished.connect(self.on_export_finished)
        self.export_thread.error.connect(self.on_export_error)
        self.export_thread.start()
        
    def on_export_finished(self, video_path):
        """Handle successful completion of video export"""
        # Re-enable export button
        for button in self.findChildren(QPushButton):
            if button.text() == "Export Video":
                button.setEnabled(True)
                break
                
        self.statusBar().showMessage(f"Video exported successfully: {video_path}")
        
    def on_export_error(self, error_msg):
        """Handle video export error"""
        # Re-enable export button
        for button in self.findChildren(QPushButton):
            if button.text() == "Export Video":
                button.setEnabled(True)
                break
                
        self.statusBar().showMessage(f"Error: {error_msg}")

def main():
    """Main entry point for the GUI application"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Karaoke Timing Editor")
    app.setApplicationVersion("1.0")
    
    # Create and show main window
    window = KaraokeEditorMainWindow()
    window.show()
    
    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 