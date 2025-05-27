import sys
import math
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QSlider, QLabel, QScrollArea, QFrame, QSpacerItem, 
                             QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPalette

class AudioTimelineWidget(QWidget):
    """
    Advanced audio timeline widget that looks like a video editor timeline.
    Features:
    - Timing markers at the top
    - Adjustable zoom (default 10 seconds visible)
    - Horizontal scrolling
    - Playhead indicator
    - Waveform visualization area
    """
    
    position_changed = pyqtSignal(float)  # Emitted when user seeks to a new position
    zoom_changed = pyqtSignal(float)      # Emitted when zoom level changes
    word_selected = pyqtSignal(object)    # Emitted when a word is selected
    word_changed = pyqtSignal(object)     # Emitted when a word timing is changed
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.audio_length = 0.0  # Total audio length in seconds
        self.current_position = 0.0  # Current playback position in seconds
        self.zoom_level = 10.0  # Seconds visible in the timeline (default 10 seconds)
        self.scroll_position = 0.0  # Horizontal scroll position in seconds
        self.word_timings = []  # List of word timing data
        
        # Word editing state
        self.selected_word_index = -1  # Index of currently selected word
        self.drag_mode = None  # None, 'move', 'resize_left', 'resize_right'
        self.drag_start_pos = None  # Starting mouse position for drag
        self.drag_start_word_data = None  # Original word data at drag start
        self.hover_word_index = -1  # Index of word being hovered over
        self.resize_threshold = 5  # Pixels from edge to trigger resize cursor
        
        # Visual settings
        self.timeline_height = 200  # Increased height for multiple tracks
        self.ruler_height = 25
        self.track_height = 40
        self.track_spacing = 5
        self.word_track_height = 35
        self.audio_track_height = 60
        
        # Colors
        self.playhead_color = QColor(255, 0, 0)  # Red playhead
        self.background_color = QColor(50, 50, 50)  # Dark background
        self.track_bg_color = QColor(40, 40, 40)  # Track background
        self.ruler_color = QColor(200, 200, 200)
        self.grid_color = QColor(80, 80, 80)
        self.waveform_color = QColor(100, 150, 255)
        self.word_color = QColor(120, 200, 120)  # Green for words
        self.word_line_end_color = QColor(200, 120, 120)  # Reddish for line end words
        self.word_border_color = QColor(80, 160, 80)
        self.word_line_end_border_color = QColor(160, 80, 80)
        self.track_label_color = QColor(180, 180, 180)
        
        self.setMinimumHeight(self.timeline_height + 80)  # Extra space for controls
        self.setup_ui()
        
        # Enable mouse tracking for seeking
        self.setMouseTracking(True)
        
    def setup_ui(self):
        """Setup the UI layout with timeline and controls"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        
        # Timeline area (will be painted directly on this widget)
        # Add spacer for timeline area
        timeline_spacer = QSpacerItem(20, self.timeline_height, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addItem(timeline_spacer)
        
        # Controls layout
        controls_layout = QHBoxLayout()
        
        # Zoom controls
        zoom_label = QLabel("Zoom:")
        controls_layout.addWidget(zoom_label)
        
        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setMaximumWidth(30)
        self.zoom_out_btn.clicked.connect(self.zoom_out)
        controls_layout.addWidget(self.zoom_out_btn)
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setMinimum(1)  # 1 second visible
        self.zoom_slider.setMaximum(120)  # 2 minutes visible
        self.zoom_slider.setValue(int(self.zoom_level))
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        self.zoom_slider.setMaximumWidth(150)
        controls_layout.addWidget(self.zoom_slider)
        
        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setMaximumWidth(30)
        self.zoom_in_btn.clicked.connect(self.zoom_in)
        controls_layout.addWidget(self.zoom_in_btn)
        
        self.zoom_level_label = QLabel(f"{self.zoom_level:.1f}s")
        controls_layout.addWidget(self.zoom_level_label)
        
        # Spacer
        controls_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Time display
        self.time_label = QLabel("00:00.0 / 00:00.0")
        self.time_label.setFont(QFont("monospace", 10))
        controls_layout.addWidget(self.time_label)
        
        # Fit to window button
        self.fit_btn = QPushButton("Fit All")
        self.fit_btn.clicked.connect(self.fit_to_window)
        controls_layout.addWidget(self.fit_btn)
        
        # Follow playhead toggle
        self.follow_playhead_btn = QPushButton("Follow Playhead")
        self.follow_playhead_btn.setCheckable(True)
        self.follow_playhead_btn.setChecked(False)  # Default to not following
        self.follow_playhead_btn.clicked.connect(self.toggle_follow_playhead)
        controls_layout.addWidget(self.follow_playhead_btn)
        
        layout.addLayout(controls_layout)
        
        # Horizontal scroll bar
        self.scroll_bar = QSlider(Qt.Orientation.Horizontal)
        self.scroll_bar.setMinimum(0)
        self.scroll_bar.setMaximum(0)
        self.scroll_bar.valueChanged.connect(self.on_scroll_changed)
        layout.addWidget(self.scroll_bar)
        
        self.setLayout(layout)
        
    def set_audio_length(self, length_seconds):
        """Set the total audio length"""
        self.audio_length = length_seconds
        self.update_scroll_range()
        self.update_time_display()
        self.update()
        
    def set_word_timings(self, word_timings):
        """Set word timing data for display"""
        self.word_timings = word_timings or []
        self.update()
        
    def set_position(self, position_seconds):
        """Set the current playback position"""
        self.current_position = max(0, min(position_seconds, self.audio_length))
        
        # Auto-scroll only if follow playhead is enabled
        if self.follow_playhead_btn.isChecked():
            if self.current_position < self.scroll_position:
                self.scroll_position = max(0, self.current_position - self.zoom_level * 0.1)
                self.update_scroll_bar_position()
            elif self.current_position > self.scroll_position + self.zoom_level:
                self.scroll_position = min(self.audio_length - self.zoom_level, 
                                         self.current_position - self.zoom_level * 0.9)
                self.update_scroll_bar_position()
        
        self.update_time_display()
        self.update()
        
    def zoom_in(self):
        """Zoom in (show less time, more detail)"""
        new_zoom = max(1.0, self.zoom_level * 0.5)
        self.set_zoom_level(new_zoom)
        
    def zoom_out(self):
        """Zoom out (show more time, less detail)"""
        new_zoom = min(120.0, self.zoom_level * 2.0)
        self.set_zoom_level(new_zoom)
        
    def fit_to_window(self):
        """Fit entire audio to window"""
        if self.audio_length > 0:
            self.set_zoom_level(self.audio_length)
            self.scroll_position = 0
            self.update_scroll_bar_position()
            
    def toggle_follow_playhead(self):
        """Toggle follow playhead mode"""
        if self.follow_playhead_btn.isChecked():
            self.follow_playhead_btn.setText("Following")
            self.follow_playhead_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        else:
            self.follow_playhead_btn.setText("Follow Playhead")
            self.follow_playhead_btn.setStyleSheet("")
            
    def set_zoom_level(self, zoom_seconds):
        """Set the zoom level (seconds visible)"""
        self.zoom_level = max(1.0, min(120.0, zoom_seconds))
        self.zoom_slider.setValue(int(self.zoom_level))
        self.zoom_level_label.setText(f"{self.zoom_level:.1f}s")
        self.update_scroll_range()
        self.zoom_changed.emit(self.zoom_level)
        self.update()
        
    def on_zoom_changed(self, value):
        """Handle zoom slider change"""
        self.set_zoom_level(float(value))
        
    def on_scroll_changed(self, value):
        """Handle scroll bar change"""
        max_scroll = max(0, self.audio_length - self.zoom_level)
        self.scroll_position = (value / 1000.0) * max_scroll
        self.update()
        
    def update_scroll_range(self):
        """Update scroll bar range based on audio length and zoom"""
        if self.audio_length <= self.zoom_level:
            self.scroll_bar.setMaximum(0)
            self.scroll_position = 0
        else:
            self.scroll_bar.setMaximum(1000)  # Use 1000 for smooth scrolling
        self.update_scroll_bar_position()
        
    def update_scroll_bar_position(self):
        """Update scroll bar position based on current scroll"""
        max_scroll = max(0, self.audio_length - self.zoom_level)
        if max_scroll > 0:
            scroll_ratio = self.scroll_position / max_scroll
            self.scroll_bar.setValue(int(scroll_ratio * 1000))
        else:
            self.scroll_bar.setValue(0)
            
    def update_time_display(self):
        """Update the time display label"""
        current_str = self.format_time(self.current_position)
        total_str = self.format_time(self.audio_length)
        self.time_label.setText(f"{current_str} / {total_str}")
        
    def format_time(self, seconds):
        """Format time in MM:SS.s format"""
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes:02d}:{secs:04.1f}"
        
    def paintEvent(self, event):
        """Custom paint event for the timeline"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate the timeline area (top part of widget, excluding controls)
        widget_rect = self.rect()
        timeline_rect = QRect(10, 10, widget_rect.width() - 20, self.timeline_height)
        
        # Fill background
        painter.fillRect(timeline_rect, self.background_color)
        
        # Draw border around timeline
        painter.setPen(QPen(QColor(100, 100, 100), 1))
        painter.drawRect(timeline_rect)
        
        if self.audio_length <= 0:
            # Draw placeholder text when no audio is loaded
            painter.setPen(QPen(QColor(150, 150, 150)))
            font = QFont("Arial", 12)
            painter.setFont(font)
            painter.drawText(timeline_rect, Qt.AlignmentFlag.AlignCenter, "Load audio to see timeline")
            return
            
        # Calculate pixels per second
        pixels_per_second = timeline_rect.width() / self.zoom_level
        
        # Draw time ruler at the top
        ruler_rect = QRect(timeline_rect.x(), timeline_rect.y(), 
                          timeline_rect.width(), self.ruler_height)
        self.draw_time_ruler(painter, ruler_rect, pixels_per_second)
        
        # Calculate track positions
        current_y = ruler_rect.bottom() + self.track_spacing
        
        # Draw word timing track
        word_track_rect = QRect(timeline_rect.x(), current_y, 
                               timeline_rect.width(), self.word_track_height)
        self.draw_word_track(painter, word_track_rect, pixels_per_second)
        current_y += self.word_track_height + self.track_spacing
        
        # Draw audio waveform track
        audio_track_rect = QRect(timeline_rect.x(), current_y, 
                                timeline_rect.width(), self.audio_track_height)
        self.draw_audio_track(painter, audio_track_rect, pixels_per_second)
        
        # Draw playhead over everything
        self.draw_playhead(painter, timeline_rect, pixels_per_second)
        
    def draw_time_ruler(self, painter, rect, pixels_per_second):
        """Draw the time ruler at the top"""
        # Fill ruler background
        painter.fillRect(rect, QColor(60, 60, 60))
        
        # Set up text drawing
        painter.setPen(QPen(self.ruler_color))
        font = QFont("Arial", 8)
        painter.setFont(font)
        font_metrics = QFontMetrics(font)
        
        # Calculate time intervals for markers
        visible_duration = self.zoom_level
        
        # Determine appropriate interval
        if visible_duration <= 10:
            major_interval = 1.0  # 1 second
            minor_interval = 0.2  # 200ms
        elif visible_duration <= 30:
            major_interval = 5.0  # 5 seconds
            minor_interval = 1.0  # 1 second
        elif visible_duration <= 120:
            major_interval = 10.0  # 10 seconds
            minor_interval = 2.0   # 2 seconds
        else:
            major_interval = 30.0  # 30 seconds
            minor_interval = 10.0  # 10 seconds
            
        # Draw time markers
        start_time = self.scroll_position
        end_time = start_time + visible_duration
        
        # Major markers
        first_major = math.ceil(start_time / major_interval) * major_interval
        current_time = first_major
        
        while current_time <= end_time:
            x = rect.x() + (current_time - start_time) * pixels_per_second
            if rect.x() <= x <= rect.x() + rect.width():
                # Draw major tick
                painter.drawLine(int(x), rect.bottom() - 12, int(x), rect.bottom())
                
                # Draw time label
                time_str = self.format_time(current_time)
                text_width = font_metrics.horizontalAdvance(time_str)
                text_x = x - text_width / 2
                if text_x >= rect.x() and text_x + text_width <= rect.x() + rect.width():
                    painter.drawText(int(text_x), rect.bottom() - 15, time_str)
                    
            current_time += major_interval
            
        # Minor markers
        painter.setPen(QPen(QColor(120, 120, 120)))
        first_minor = math.ceil(start_time / minor_interval) * minor_interval
        current_time = first_minor
        
        while current_time <= end_time:
            x = rect.x() + (current_time - start_time) * pixels_per_second
            if rect.x() <= x <= rect.x() + rect.width():
                # Skip if this is a major marker
                if abs(current_time % major_interval) > 0.001:
                    painter.drawLine(int(x), rect.bottom() - 6, int(x), rect.bottom())
                    
            current_time += minor_interval
            
    def draw_word_track(self, painter, rect, pixels_per_second):
        """Draw the word timing track"""
        # Fill track background
        painter.fillRect(rect, self.track_bg_color)
        
        # Draw track label
        painter.setPen(QPen(self.track_label_color))
        font = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect.x() + 5, rect.y() + 12, "Words")
        
        # Draw word timing blocks
        if self.word_timings:
            start_time = self.scroll_position
            end_time = start_time + self.zoom_level
            
            for word_index, word_data in enumerate(self.word_timings):
                # Handle different field names for timing data
                word_start = word_data.get('start', word_data.get('begin', 0))
                word_end = word_data.get('end', word_data.get('end', 0))
                word_text = word_data.get('word', word_data.get('text', ''))
                is_line_end = word_data.get('line_end', False)
                
                # Skip words outside visible range
                if word_end < start_time or word_start > end_time:
                    continue
                    
                # Calculate word block position and size
                block_start_x = rect.x() + max(0, (word_start - start_time) * pixels_per_second)
                block_end_x = rect.x() + min(rect.width(), (word_end - start_time) * pixels_per_second)
                block_width = max(2, block_end_x - block_start_x)  # Minimum 2 pixels wide
                
                # Draw word block
                word_rect = QRect(int(block_start_x), rect.y() + 15, 
                                 int(block_width), rect.height() - 20)
                
                # Choose colors based on selection, hover state, and line end status
                if word_index == self.selected_word_index:
                    # Selected word - use bright highlight
                    fill_color = QColor(255, 200, 100)  # Bright orange
                    border_color = QColor(255, 150, 0)  # Orange border
                    border_width = 2
                elif word_index == self.hover_word_index:
                    # Hovered word - use lighter highlight
                    if is_line_end:
                        fill_color = QColor(220, 150, 150)  # Light red
                        border_color = QColor(180, 100, 100)  # Red border
                    else:
                        fill_color = QColor(150, 220, 150)  # Light green
                        border_color = QColor(100, 180, 100)  # Green border
                    border_width = 2
                else:
                    # Normal word
                    if is_line_end:
                        fill_color = self.word_line_end_color
                        border_color = self.word_line_end_border_color
                    else:
                        fill_color = self.word_color
                        border_color = self.word_border_color
                    border_width = 1
                
                # Fill word block
                painter.fillRect(word_rect, fill_color)
                
                # Draw word block border
                painter.setPen(QPen(border_color, border_width))
                painter.drawRect(word_rect)
                
                # Draw word text - be more aggressive about showing text
                if block_width > 8:  # Show text even in very small blocks
                    painter.setPen(QPen(QColor(0, 0, 0)))  # Black text
                    
                    # Use smaller font for narrow blocks
                    if block_width < 20:
                        font = QFont("Arial", 6)  # Smaller font for tight spaces
                    elif block_width < 40:
                        font = QFont("Arial", 7)  # Regular small font
                    else:
                        font = QFont("Arial", 8)  # Slightly larger for wider blocks
                    
                    painter.setFont(font)
                    font_metrics = QFontMetrics(font)
                    
                    # Use minimal padding (1 pixel on each side)
                    available_width = block_width - 2
                    display_text = word_text
                    
                    # Check if we need to truncate
                    text_width = font_metrics.horizontalAdvance(display_text)
                    if text_width > available_width:
                        # For very small spaces, show just first few characters
                        if available_width < 15:
                            # Show as many characters as possible without ellipsis
                            while len(display_text) > 1 and font_metrics.horizontalAdvance(display_text) > available_width:
                                display_text = display_text[:-1]
                        else:
                            # Use ellipsis for larger spaces
                            ellipsis_width = font_metrics.horizontalAdvance("...")
                            target_width = available_width - ellipsis_width
                            
                            while len(display_text) > 1 and font_metrics.horizontalAdvance(display_text) > target_width:
                                display_text = display_text[:-1]
                            
                            if len(display_text) < len(word_text):
                                display_text += "..."
                    
                    # Center the text in the available space
                    final_text_width = font_metrics.horizontalAdvance(display_text)
                    text_x = word_rect.x() + (word_rect.width() - final_text_width) // 2
                    text_y = word_rect.y() + word_rect.height() // 2 + font_metrics.ascent() // 2
                    
                    painter.drawText(text_x, text_y, display_text)
    
    def draw_audio_track(self, painter, rect, pixels_per_second):
        """Draw the audio waveform track"""
        # Fill track background
        painter.fillRect(rect, self.track_bg_color)
        
        # Draw track label
        painter.setPen(QPen(self.track_label_color))
        font = QFont("Arial", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect.x() + 5, rect.y() + 15, "Audio")
        
        # Draw audio bar representing the full audio length
        audio_bar_rect = QRect(rect.x() + 60, rect.y() + 10, rect.width() - 70, rect.height() - 20)
        
        # Fill audio bar with a gradient or solid color
        painter.fillRect(audio_bar_rect, QColor(70, 130, 180))  # Steel blue color
        
        # Draw border around audio bar
        painter.setPen(QPen(QColor(50, 100, 150), 2))
        painter.drawRect(audio_bar_rect)
        
        # Draw grid lines over the audio bar
        painter.setPen(QPen(self.grid_color, 1, Qt.PenStyle.DotLine))
        
        # Vertical grid lines (every second)
        start_time = self.scroll_position
        end_time = start_time + self.zoom_level
        
        current_time = math.ceil(start_time)
        while current_time <= end_time:
            x = rect.x() + 60 + (current_time - start_time) * pixels_per_second
            if audio_bar_rect.left() <= x <= audio_bar_rect.right():
                painter.drawLine(int(x), audio_bar_rect.top(), int(x), audio_bar_rect.bottom())
            current_time += 1.0
        
    def draw_placeholder_waveform(self, painter, rect, pixels_per_second):
        """Draw a placeholder waveform pattern"""
        center_y = rect.center().y()
        
        # Generate a simple sine wave pattern as placeholder
        for x in range(rect.left(), rect.right(), 2):
            time_pos = self.scroll_position + (x - rect.left()) / pixels_per_second
            
            # Create a pseudo-random waveform based on time position
            amplitude = 20 * (0.5 + 0.3 * math.sin(time_pos * 2) + 0.2 * math.sin(time_pos * 7))
            y1 = center_y - amplitude
            y2 = center_y + amplitude
            
            painter.drawLine(x, int(y1), x, int(y2))
            
    def draw_playhead(self, painter, rect, pixels_per_second):
        """Draw the playhead indicator"""
        if self.current_position < self.scroll_position or \
           self.current_position > self.scroll_position + self.zoom_level:
            return  # Playhead is not visible
            
        x = rect.x() + (self.current_position - self.scroll_position) * pixels_per_second
        
        # Draw playhead line
        painter.setPen(QPen(self.playhead_color, 2))
        painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
        
        # Draw playhead triangle at top
        triangle_size = 8
        triangle_points = [
            QPoint(int(x), rect.top()),
            QPoint(int(x - triangle_size/2), rect.top() + triangle_size),
            QPoint(int(x + triangle_size/2), rect.top() + triangle_size)
        ]
        
        painter.setBrush(QBrush(self.playhead_color))
        painter.setPen(QPen(self.playhead_color))
        painter.drawPolygon(triangle_points)
        
    def mousePressEvent(self, event):
        """Handle mouse press for seeking and word editing"""
        if event.button() == Qt.MouseButton.LeftButton:
            mouse_x, mouse_y = event.pos().x(), event.pos().y()
            
            # Check if clicking on a word
            word_index, word_rect = self.get_word_at_position(mouse_x, mouse_y)
            
            if word_index >= 0:
                # Clicking on a word - start editing
                # Only update selection if clicking on a different word
                if word_index != self.selected_word_index:
                    self.set_selected_word(word_index)
                self.drag_mode = self.get_resize_mode(mouse_x, word_rect)
                self.drag_start_pos = event.pos()
                self.drag_start_word_data = self.word_timings[word_index].copy()
                
                # Set appropriate cursor
                if self.drag_mode == 'resize_left' or self.drag_mode == 'resize_right':
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                    
            else:
                # Not clicking on a word - check if in timeline for seeking
                widget_rect = self.rect()
                timeline_rect = QRect(10, 10, widget_rect.width() - 20, self.timeline_height)
                
                if timeline_rect.contains(event.pos()) and self.audio_length > 0:
                    # Calculate clicked time position for seeking
                    relative_x = event.pos().x() - timeline_rect.x()
                    pixels_per_second = timeline_rect.width() / self.zoom_level
                    clicked_time = self.scroll_position + (relative_x / pixels_per_second)
                    
                    # Apply snap-to-grid based on zoom level
                    if self.zoom_level <= 10:  # When zoomed in close
                        snap_interval = 0.05  # Snap to 100ms intervals
                    elif self.zoom_level <= 30:
                        snap_interval = 0.5  # Snap to 500ms intervals
                    else:
                        snap_interval = 1.0  # Snap to 1s intervals
                    
                    # Calculate snapped position
                    snapped_time = round(clicked_time / snap_interval) * snap_interval
                    
                    # Clamp to valid range
                    snapped_time = max(0, min(snapped_time, self.audio_length))
                    
                    # Emit position change signal
                    self.position_changed.emit(snapped_time)
                
                # Don't deselect the current word when clicking away
                # Only deselect if explicitly selecting a different word
                
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for word editing and cursor updates"""
        mouse_x, mouse_y = event.pos().x(), event.pos().y()
        
        if self.drag_mode and self.drag_start_pos:
            # Currently dragging a word
            widget_rect = self.rect()
            timeline_rect = QRect(10, 10, widget_rect.width() - 20, self.timeline_height)
            pixels_per_second = timeline_rect.width() / self.zoom_level
            
            # Calculate time delta
            dx = event.pos().x() - self.drag_start_pos.x()
            time_delta = dx / pixels_per_second
            
            # Get original word timing
            orig_start = self.drag_start_word_data.get('start', self.drag_start_word_data.get('begin', 0))
            orig_end = self.drag_start_word_data.get('end', self.drag_start_word_data.get('end', 0))
            
            if self.drag_mode == 'move':
                # Move entire word
                new_start = max(0, orig_start + time_delta)
                new_end = min(self.audio_length, orig_end + time_delta)
                
                # Ensure word doesn't get smaller than minimum size
                min_duration = 0.05  # 50ms minimum
                if new_end - new_start < min_duration:
                    if new_start == 0:
                        new_end = new_start + min_duration
                    elif new_end == self.audio_length:
                        new_start = new_end - min_duration
                        
            elif self.drag_mode == 'resize_left':
                # Resize left edge
                new_start = max(0, min(orig_start + time_delta, orig_end - 0.05))
                new_end = orig_end
                
            elif self.drag_mode == 'resize_right':
                # Resize right edge
                new_start = orig_start
                new_end = min(self.audio_length, max(orig_end + time_delta, orig_start + 0.05))
            
            # Update word timing
            if self.selected_word_index >= 0:
                self.update_word_timing(self.selected_word_index, new_start, new_end)
        
        else:
            # Not dragging - update hover state and cursor
            word_index, word_rect = self.get_word_at_position(mouse_x, mouse_y)
            
            # Update hover state
            if word_index != self.hover_word_index:
                self.hover_word_index = word_index
                self.update()
            
            # Update cursor based on hover position
            if word_index >= 0:
                resize_mode = self.get_resize_mode(mouse_x, word_rect)
                if resize_mode == 'resize_left' or resize_mode == 'resize_right':
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
                else:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        
        super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to end word editing"""
        if event.button() == Qt.MouseButton.LeftButton:
            if self.drag_mode:
                # End drag operation
                self.drag_mode = None
                self.drag_start_pos = None
                self.drag_start_word_data = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
        
        super().mouseReleaseEvent(event)
        
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming and scrolling"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom with Ctrl+Wheel (vertical scrolling)
            delta_y = event.angleDelta().y()
            if delta_y > 0:
                self.zoom_in_at_position(event.position().x())
            else:
                self.zoom_out_at_position(event.position().x())
        else:
            # Handle horizontal scrolling
            delta_x = event.angleDelta().x()  # Horizontal wheel movement
            delta_y = event.angleDelta().y()  # Vertical wheel movement
            
            # Use horizontal wheel if available, otherwise fall back to vertical
            if delta_x != 0:
                # Horizontal wheel scrolling (sideways scroll wheel)
                scroll_amount = self.zoom_level * 0.1  # 10% of visible duration
                
                # Invert the scrolling: positive delta_x scrolls left, negative scrolls right
                if delta_x > 0:
                    # Scroll left (backward in time)
                    new_scroll = max(0, self.scroll_position - scroll_amount)
                else:
                    # Scroll right (forward in time)
                    max_scroll = max(0, self.audio_length - self.zoom_level)
                    new_scroll = min(max_scroll, self.scroll_position + scroll_amount)
                    
                self.scroll_position = new_scroll
                self.update_scroll_bar_position()
                self.update()
                
            elif delta_y != 0:
                # Vertical wheel now controls zoom
                if delta_y > 0:
                    self.zoom_in_at_position(event.position().x())
                else:
                    self.zoom_out_at_position(event.position().x())
            
        event.accept()

    def zoom_in_at_position(self, mouse_x):
        """Zoom in centered on mouse position"""
        if self.audio_length <= 0:
            return

        # Calculate the time position under the mouse
        widget_rect = self.rect()
        timeline_rect = QRect(10, 10, widget_rect.width() - 20, self.timeline_height)
        pixels_per_second = timeline_rect.width() / self.zoom_level
        mouse_time = self.scroll_position + (mouse_x - timeline_rect.x()) / pixels_per_second

        # Calculate new zoom level
        new_zoom = max(1.0, self.zoom_level * 0.5)

        # Calculate new scroll position to keep mouse position fixed
        new_pixels_per_second = timeline_rect.width() / new_zoom
        new_scroll = mouse_time - (mouse_x - timeline_rect.x()) / new_pixels_per_second

        # Apply changes
        self.set_zoom_level(new_zoom)
        self.scroll_position = max(0, min(new_scroll, self.audio_length - new_zoom))
        self.update_scroll_bar_position()
        self.update()

    def zoom_out_at_position(self, mouse_x):
        """Zoom out centered on mouse position"""
        if self.audio_length <= 0:
            return

        # Calculate the time position under the mouse
        widget_rect = self.rect()
        timeline_rect = QRect(10, 10, widget_rect.width() - 20, self.timeline_height)
        pixels_per_second = timeline_rect.width() / self.zoom_level
        mouse_time = self.scroll_position + (mouse_x - timeline_rect.x()) / pixels_per_second

        # Calculate new zoom level
        new_zoom = min(120.0, self.zoom_level * 2.0)

        # Calculate new scroll position to keep mouse position fixed
        new_pixels_per_second = timeline_rect.width() / new_zoom
        new_scroll = mouse_time - (mouse_x - timeline_rect.x()) / new_pixels_per_second

        # Apply changes
        self.set_zoom_level(new_zoom)
        self.scroll_position = max(0, min(new_scroll, self.audio_length - new_zoom))
        self.update_scroll_bar_position()
        self.update()

    def get_position(self):
        """Get the current playhead position in seconds"""
        return self.current_position
    
    def get_word_at_position(self, mouse_x, mouse_y):
        """Find which word is at the given mouse position"""
        # Calculate if mouse is in word track area
        widget_rect = self.rect()
        timeline_rect = QRect(10, 10, widget_rect.width() - 20, self.timeline_height)
        
        # Calculate word track position (same as in paintEvent)
        ruler_rect = QRect(timeline_rect.x(), timeline_rect.y(), 
                          timeline_rect.width(), self.ruler_height)
        word_track_y = ruler_rect.bottom() + self.track_spacing
        word_track_rect = QRect(timeline_rect.x(), word_track_y, 
                               timeline_rect.width(), self.word_track_height)
        
        # Check if mouse is in word track
        if not word_track_rect.contains(mouse_x, mouse_y):
            return -1, None
        
        if not self.word_timings or self.audio_length <= 0:
            return -1, None
            
        # Calculate time from mouse position
        pixels_per_second = timeline_rect.width() / self.zoom_level
        start_time = self.scroll_position
        end_time = start_time + self.zoom_level
        
        for word_index, word_data in enumerate(self.word_timings):
            word_start = word_data.get('start', word_data.get('begin', 0))
            word_end = word_data.get('end', word_data.get('end', 0))
            
            # Skip words outside visible range
            if word_end < start_time or word_start > end_time:
                continue
                
            # Calculate word block position
            block_start_x = timeline_rect.x() + max(0, (word_start - start_time) * pixels_per_second)
            block_end_x = timeline_rect.x() + min(timeline_rect.width(), (word_end - start_time) * pixels_per_second)
            
            word_rect = QRect(int(block_start_x), word_track_y + 15, 
                             int(block_end_x - block_start_x), self.word_track_height - 20)
            
            if word_rect.contains(mouse_x, mouse_y):
                return word_index, word_rect
                
        return -1, None
    
    def get_resize_mode(self, mouse_x, word_rect):
        """Determine if mouse is near word edges for resizing"""
        if mouse_x <= word_rect.left() + self.resize_threshold:
            return 'resize_left'
        elif mouse_x >= word_rect.right() - self.resize_threshold:
            return 'resize_right'
        else:
            return 'move'
    
    def update_word_timing(self, word_index, new_start, new_end):
        """Update word timing and emit change signal"""
        if 0 <= word_index < len(self.word_timings):
            word_data = self.word_timings[word_index].copy()
            
            # Update timing fields (handle different field names)
            if 'start' in word_data:
                word_data['start'] = new_start
            elif 'begin' in word_data:
                word_data['begin'] = new_start
                
            if 'end' in word_data:
                word_data['end'] = new_end
            elif 'end' in word_data:  # This should always be true, but keeping consistent
                word_data['end'] = new_end
            
            # Update the timing data
            self.word_timings[word_index] = word_data
            
            # Emit change signal
            self.word_changed.emit(word_data)
            
            # Trigger redraw
            self.update()
    
    def set_selected_word(self, word_index):
        """Set the selected word and emit selection signal"""
        if word_index != self.selected_word_index:
            self.selected_word_index = word_index
            
            if 0 <= word_index < len(self.word_timings):
                self.word_selected.emit(self.word_timings[word_index])
            else:
                self.word_selected.emit(None)
            
            self.update()


# Test application
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Create test window
    widget = AudioTimelineWidget()
    widget.setWindowTitle("Audio Timeline Widget Test")
    widget.resize(800, 200)
    
    # Set test audio length (5 minutes)
    widget.set_audio_length(300.0)
    
    # Simulate playback position updates
    timer = QTimer()
    position = [0.0]
    
    def update_position():
        position[0] += 0.1
        if position[0] > 300.0:
            position[0] = 0.0
        widget.set_position(position[0])
    
    timer.timeout.connect(update_position)
    timer.start(100)
    
    # Connect signals
    widget.position_changed.connect(lambda pos: print(f"Seek to: {pos:.2f}s"))
    widget.zoom_changed.connect(lambda zoom: print(f"Zoom changed: {zoom:.1f}s"))
    
    widget.show()
    sys.exit(app.exec()) 