import os
import json
import math
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple

import dotenv
dotenv.load_dotenv(dotenv_path='.env')

# Load font configurations from environment variables (same keys as MoviePy impl)
FONT_NAME = os.getenv('FONT_NAME', 'Cascadia-Mono-Regular')
FONT_COLOR_ACTIVE = os.getenv('FONT_COLOR_ACTIVE', 'yellow')
FONT_COLOR_INACTIVE = os.getenv('FONT_COLOR_INACTIVE', 'white')
FONT_KERNING = int(os.getenv('FONT_KERNING', '1'))  # Not directly used by ASS, kept for compatibility
FONTS_DIR = os.getenv('FONTS_DIR', None)  # Optional directory for libass to find fonts


def _parse_resolution(resolution: str | int | Tuple[int, int]) -> Tuple[int, int, float]:
    """Parse resolution into (width, height, scale_factor) assuming 16:9 if height provided.

    Returns scale_factor relative to 720p height for consistent sizing.
    """
    if isinstance(resolution, (tuple, list)) and len(resolution) == 2:
        width, height = int(resolution[0]), int(resolution[1])
    elif isinstance(resolution, str):
        if 'x' in resolution:
            width, height = map(int, resolution.split('x'))
        else:
            height = int(resolution)
            width = int(height * 16 / 9)
    else:
        height = int(resolution)
        width = int(height * 16 / 9)

    # Enforce 16:9
    if width / height != 16 / 9:
        if width / height > 16 / 9:
            width = int(height * 16 / 9)
        else:
            height = int(width * 9 / 16)

    scale_factor = height / 720.0
    return width, height, scale_factor


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS time h:mm:ss.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - math.floor(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_color_from_name(name_or_hex: str) -> Tuple[int, int, int]:
    """Resolve a simple color name or #RRGGBB into an (R, G, B) tuple.
    This is intentionally simple; extend if needed.
    """
    named = {
        'white': (255, 255, 255),
        'black': (0, 0, 0),
        'yellow': (255, 255, 0),
        'red': (255, 0, 0),
        'green': (0, 255, 0),
        'blue': (0, 0, 255),
    }
    val = name_or_hex.strip().lower()
    if val in named:
        return named[val]
    if val.startswith('#') and len(val) == 7:
        r = int(val[1:3], 16)
        g = int(val[3:5], 16)
        b = int(val[5:7], 16)
        return r, g, b
    # Fallback to white
    return (255, 255, 255)


def _ass_bgr_hex(color_rgb: Tuple[int, int, int]) -> str:
    """ASS uses BGR order in hex, format: &HBBGGRR&"""
    r, g, b = color_rgb
    return f"&H{b:02X}{g:02X}{r:02X}&"


class KaraokeVideoGenerator:
    """
    ASS/NVENC-based generator. Matches the public API of the MoviePy generator so it can be swapped in.
    - Builds an .ass file with \\kf word-level karaoke
    - Renders with ffmpeg using a GPU encoder (h264_nvenc)
    - Uses a black background source at the requested resolution
    """

    def __init__(self, output_dir: str, resolution: str | int | Tuple[int, int] = "1280x720") -> None:
        self.output_dir = output_dir
        self.width, self.height, self.scale_factor = _parse_resolution(resolution)

        # Scaled typography
        self.font_size = int(50 * self.scale_factor)
        # Thicker outline for readability (ASS Outline thickness)
        self.outline_width = max(2, int(3 * self.scale_factor))

        # Y margins (top/bottom alignment styles will respect MarginV)
        self.margin_v = int(80 * self.scale_factor)

    def generate(
        self,
        instrumental_path: str,
        alignment_path: str,
        output_name: str,
        use_wipe: bool = True,
        song_title: str = "",
        artist: str = "",
    ) -> str:
        # Load alignment
        with open(alignment_path, 'r', encoding='utf-8') as f:
            alignment_data = json.load(f)

        # Group into lines
        lines = self._group_words_into_lines(alignment_data)

        # Determine audio duration (prefer ffprobe; avoid heavy decoders)
        duration = self._probe_audio_duration(instrumental_path)

        # Build .ass content
        ass_content = self._build_ass_content(lines, duration, song_title, artist)

        # Write .ass file alongside output
        os.makedirs(self.output_dir, exist_ok=True)
        sanitized_name = "".join(c for c in output_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        ass_path = os.path.join(self.output_dir, f"{sanitized_name}.ass")
        with open(ass_path, 'w', encoding='utf-8') as f:
            f.write(ass_content)

        # Render with ffmpeg using NVENC
        output_path = os.path.join(self.output_dir, f"{sanitized_name}.mp4")

        # Use working directory to simplify subtitles path escaping on Windows
        wd = str(Path(self.output_dir).resolve())
        ass_file_name = os.path.basename(ass_path)

        vf_expr = f"subtitles={ass_file_name}"
        if FONTS_DIR:
            # Use only the directory name in cwd context
            fontsdir_rel = os.path.relpath(Path(FONTS_DIR).resolve(), Path(wd))
            vf_expr = f"subtitles={ass_file_name}:fontsdir={fontsdir_rel}"

        ffmpeg_cmd = [
            'ffmpeg',
            '-y',
            # background (black) video source at desired size/duration
            '-f', 'lavfi', '-i', f"color=c=black:s={self.width}x{self.height}:d={duration:.3f}",
            # audio input
            '-i', instrumental_path,
            # structured progress to stdout
            '-progress', 'pipe:1',
            '-nostats',
            # subtitles overlay
            '-vf', vf_expr,
            # video encode (NVENC)
            '-c:v', 'h264_nvenc',
            '-preset', 'p5',
            '-rc', 'vbr',
            '-cq', '21',
            '-b:v', '0',
            '-bf', '2',
            '-g', '48',
            '-pix_fmt', 'yuv420p',
            # audio encode
            '-c:a', 'aac', '-b:a', '192k',
            # ensure we stop at audio end
            '-shortest',
            output_path,
        ]

        print(f"Rendering with ffmpeg (NVENC) to: {output_path}")

        # Run ffmpeg and parse progress
        proc = subprocess.Popen(
            ffmpeg_cmd,
            cwd=wd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        last_percent = -1
        out_time_sec = 0.0
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                # Expect key=value pairs from -progress
                if '=' in line:
                    key, val = line.split('=', 1)
                    if key == 'out_time_ms':
                        try:
                            out_time_sec = max(out_time_sec, int(val) / 1_000_000.0)
                        except ValueError:
                            pass
                    elif key == 'out_time':
                        # Format HH:MM:SS.micro
                        try:
                            h, m, s = val.split(':')
                            sec = float(s)
                            out_time_sec = max(out_time_sec, int(h) * 3600 + int(m) * 60 + sec)
                        except Exception:
                            pass
                    elif key == 'progress' and val in ('continue', 'end'):
                        # Compute percent and report
                        if duration > 0:
                            percent = int(min(100, (out_time_sec / duration) * 100))
                            if percent != last_percent:
                                last_percent = percent
                                cur = _format_ass_time(out_time_sec)
                                total = _format_ass_time(duration)
                                print(f"ffmpeg progress: {percent}% ({cur}/{total})")
        finally:
            proc.wait()

        if proc.returncode != 0:
            # Try a CPU fallback if NVENC not available
            stderr_text = proc.stderr.read() if proc.stderr else ''
            print("NVENC failed, falling back to libx264. Error:\n" + stderr_text)
            ffmpeg_cmd_fallback = ffmpeg_cmd.copy()
            # replace codec args
            idx = ffmpeg_cmd_fallback.index('h264_nvenc')
            ffmpeg_cmd_fallback[idx] = 'libx264'
            # remove NVENC-only rate control settings not applicable to libx264
            # Keep a similar quality target via -preset veryfast
            cleaned = []
            skip_next = False
            skip_keys = {'-rc', '-cq'}
            for i, tok in enumerate(ffmpeg_cmd_fallback):
                if skip_next:
                    skip_next = False
                    continue
                if tok in skip_keys:
                    skip_next = True
                    continue
                cleaned.append(tok)
            # Insert x264 preset
            try:
                ci = cleaned.index('libx264')
                cleaned.insert(ci + 1, '-preset')
                cleaned.insert(ci + 2, 'veryfast')
            except ValueError:
                pass

            proc2 = subprocess.Popen(
                cleaned, cwd=wd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True
            )
            last_percent = -1
            out_time_sec = 0.0
            try:
                assert proc2.stdout is not None
                for line in proc2.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        if key == 'out_time_ms':
                            try:
                                out_time_sec = max(out_time_sec, int(val) / 1_000_000.0)
                            except ValueError:
                                pass
                        elif key == 'out_time':
                            try:
                                h, m, s = val.split(':')
                                sec = float(s)
                                out_time_sec = max(out_time_sec, int(h) * 3600 + int(m) * 60 + sec)
                            except Exception:
                                pass
                        elif key == 'progress' and val in ('continue', 'end'):
                            if duration > 0:
                                percent = int(min(100, (out_time_sec / duration) * 100))
                                if percent != last_percent:
                                    last_percent = percent
                                    cur = _format_ass_time(out_time_sec)
                                    total = _format_ass_time(duration)
                                    print(f"ffmpeg progress: {percent}% ({cur}/{total})")
            finally:
                proc2.wait()
            if proc2.returncode != 0:
                stderr2 = proc2.stderr.read() if proc2.stderr else ''
                raise RuntimeError(f"ffmpeg failed:\n{stderr_text}\n--- fallback ---\n{stderr2}")

        return output_path

    # ---------- Internal helpers ----------

    def _group_words_into_lines(self, alignment_data: List[Dict]) -> List[Dict]:
        lines: List[Dict] = []
        current_line: List[Dict] = []
        for word in alignment_data:
            if word.get('begin') is None or word.get('end') is None:
                continue
            current_line.append(word)
            if word.get('line_end', False):
                if current_line:
                    line_start = min(float(w['begin']) for w in current_line)
                    line_end = max(float(w['end']) for w in current_line)
                    line_text = ' '.join(w['text'] for w in current_line)
                    lines.append({
                        'words': current_line.copy(),
                        'text': line_text,
                        'start': line_start,
                        'end': line_end,
                        'line_number': len(lines),
                    })
                    current_line = []
        if current_line:
            line_start = min(float(w['begin']) for w in current_line)
            line_end = max(float(w['end']) for w in current_line)
            line_text = ' '.join(w['text'] for w in current_line)
            lines.append({
                'words': current_line.copy(),
                'text': line_text,
                'start': line_start,
                'end': line_end,
                'line_number': len(lines),
            })
        return lines

    def _preprocess_line_text(self, line_text: str, max_chars_per_line: int = 40) -> str:
        words = line_text.split()
        if not words:
            return line_text
        lines: List[str] = []
        current: List[str] = []
        current_len = 0
        for w in words:
            add = (1 if current else 0) + len(w)
            if current_len + add <= max_chars_per_line:
                current.append(w)
                current_len += add
            else:
                if current:
                    lines.append(' '.join(current))
                current = [w]
                current_len = len(w)
        if current:
            lines.append(' '.join(current))
        return '\\N'.join(lines)  # ASS newline

    def _build_ass_header(self) -> str:
        # Colors
        active_rgb = _hex_color_from_name(FONT_COLOR_ACTIVE)
        inactive_rgb = _hex_color_from_name(FONT_COLOR_INACTIVE)
        primary = _ass_bgr_hex(active_rgb)
        secondary = _ass_bgr_hex(inactive_rgb)
        outline = _ass_bgr_hex((0, 0, 0))

        # Style template: Primary is highlighted karaoke color, Secondary is base text color
        base_style = (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )

        style_top = (
            f"Style: KaraokeTop,{FONT_NAME},{self.font_size},{primary},{secondary},{outline},&H00000000,"
            f"0,0,0,0,100,100,0,0,1,{self.outline_width},1,8,20,20,{self.margin_v},1\n"
        )
        style_bottom = (
            f"Style: KaraokeBottom,{FONT_NAME},{self.font_size},{primary},{secondary},{outline},&H00000000,"
            f"0,0,0,0,100,100,0,0,1,{self.outline_width},1,2,20,20,{self.margin_v},1\n"
        )
        style_center = (
            f"Style: KaraokeCenter,{FONT_NAME},{self.font_size},{secondary},{secondary},{outline},&H00000000,"
            f"0,0,0,0,100,100,0,0,1,{self.outline_width},1,5,20,20,{self.margin_v},1\n"
        )

        header = (
            "[Script Info]\n"
            f"; Script generated by Karaoke-maker (ASS generator)\n"
            f"ScaledBorderAndShadow: yes\n"
            f"PlayResX: {self.width}\n"
            f"PlayResY: {self.height}\n"
            "WrapStyle: 0\n"
            "YCbCr Matrix: TV.709\n\n"
            "[V4+ Styles]\n" + base_style + style_top + style_bottom + style_center + "\n"
            "[Events]\n"
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        )
        return header

    def _build_ass_content(self, lines: List[Dict], duration: float, song_title: str, artist: str) -> str:
        header = self._build_ass_header()
        events: List[str] = []

        # Intro title if there is at least 5s before first line, else optional 5s intro
        first_line_start = lines[0]['start'] if lines else 0.0
        if song_title:
            title_text = song_title
            if artist:
                title_text += f"\\N{artist}"
            if first_line_start >= 5.0:
                start, end = max(0.0, first_line_start - 4.0), max(0.0, first_line_start - 1.0)
            else:
                start, end = 0.5, 5.5
            events.append(self._dialogue_line(start, end, 'KaraokeCenter', title_text))

        # Main lines
        for i, line in enumerate(lines):
            is_top = (i % 2 == 0)
            style = 'KaraokeTop' if is_top else 'KaraokeBottom'
            text = self._preprocess_line_text(line['text'].upper())

            # Add readability padding before/after the line window
            base_start = max(0.0, float(line['start']))
            base_end = float(line['end'])
            pad_before = 0.6
            pad_after = 0.4
            start_time = max(0.0, base_start - pad_before)
            end_time = base_end + pad_after
            line_duration = max(0.01, end_time - start_time)

            # Build \kf karaoke per word
            words = [w for w in line['words'] if w.get('begin') is not None and w.get('end') is not None]
            if not words:
                events.append(self._dialogue_line(start_time, end_time, style, text))
                continue

            # Build \kf with explicit pre/post padding as dummy syllables
            kf_parts: List[str] = []
            lead_cs = max(0, int(round((base_start - start_time) * 100)))
            tail_cs = max(0, int(round((end_time - base_end) * 100)))
            if lead_cs > 0:
                kf_parts.append(f"{{\\kf{lead_cs}}} ")

            prev_end = base_start
            for w in words:
                # Keep \kf timing accurate by anchoring to original word times within padded window
                w_start = max(start_time, float(w['begin']))
                w_end = min(end_time, float(w['end']))
                dur_cs = max(1, int(round((w_end - w_start) * 100)))
                # If there is a gap from previous word end to this word start, add a space with \kf for the gap
                gap_sec = float(w['begin']) - prev_end
                if gap_sec > 0.0:
                    gap_cs = int(round(gap_sec * 100))
                    # timed space for the gap
                    kf_parts.append(f"{{\\kf{gap_cs}}} ")
                else:
                    # ensure single space between words when no timed gap
                    if kf_parts and not kf_parts[-1].endswith(' '):
                        kf_parts.append(' ')
                kf_parts.append(f"{{\\kf{dur_cs}}}{str(w['text']).upper()}")
                prev_end = float(w['end'])

            if tail_cs > 0:
                kf_parts.append(f" {{\\kf{tail_cs}}} ")

            # Concatenate tokens directly to avoid double spaces
            kf_text = ''.join(kf_parts)

            # Keep the dialogue visible through the padded window
            events.append(self._dialogue_line(start_time, end_time, style, kf_text))

            # Optional long gap message
            if i < len(lines) - 1:
                gap = float(lines[i+1]['start']) - float(line['end'])
                if gap > 10.0:
                    gap_text = f"[{int(gap)} second break]"
                    events.append(self._dialogue_line(float(line['end']) + 1.0, float(lines[i+1]['start']) - 1.0, 'KaraokeCenter', gap_text))

        # Outro message if audio significantly longer than last line
        if lines:
            last_end = float(lines[-1]['end'])
            outro_dur = duration - last_end
            if outro_dur > 10.0:
                outro_text = f"[{int(outro_dur)} second outro]"
                events.append(self._dialogue_line(last_end + 2.0, min(duration, last_end + outro_dur - 2.0), 'KaraokeCenter', outro_text))

        return header + "\n".join(events) + "\n"

    def _dialogue_line(self, start: float, end: float, style: str, text: str) -> str:
        start_str = _format_ass_time(start)
        end_str = _format_ass_time(end)
        # Escape commas in text (ASS uses commas as field separators). Newlines already encoded as \N.
        safe_text = text.replace(',', '\\,')
        return f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{safe_text}"

    def _probe_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds using ffprobe; fallback to a fixed value on failure."""
        try:
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
            dur = float(out.strip())
            if dur > 0:
                return dur
        except Exception as e:
            print(f"ffprobe failed to get duration, defaulting to 300s: {e}")
        return 300.0

