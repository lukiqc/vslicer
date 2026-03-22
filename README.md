# VSlicer

A lightweight, frame-accurate video clipping tool that lets you precisely select and export clips from video URLs using mpv and ffmpeg.

## Features

- **Frame-accurate navigation** - Step through videos frame-by-frame
- **IN/OUT point marking** - Precise clip boundary selection
- **Slow-motion export** - Apply slow-motion effects with audio stretching
- **Crop for vertical video** - Convert landscape to portrait (9:16, 4:5, 1:1, or custom)
- **Visual crop preview** - Draggable overlay shows exact crop region
- **Embedded video playback** - Video plays directly in the GUI window
- **CLI and GUI** - Terminal interface and graphical Qt-based interface
- **Cross-platform** - Works on Linux, WSL, Windows, and macOS
- **Minimal dependencies** - Just mpv and ffmpeg

## Installation

### Prerequisites

**System dependencies:**
- **mpv** (with IPC support) - for video playback
- **ffmpeg** (with libvpx-vp9 and libopus) - for video processing
- **Python 3.12+**

**Installing system dependencies:**

```bash
# Linux/WSL
sudo apt update
sudo apt install -y mpv ffmpeg

# macOS
brew install mpv ffmpeg

# Windows
# Download from mpv.io and ffmpeg.org, or use chocolatey:
choco install mpv ffmpeg
```

### Installing VSlicer

**Windows (GUI):**
```
1. git clone <repository-url>
2. Double-click install.bat  (installs mpv, ffmpeg, and Python dependencies)
3. Double-click windows_gui.bat  (launches the GUI — no terminal window)
```
> Requires Python 3.12+ to be installed first. `install.bat` handles everything else automatically.

**Linux / macOS / devcontainer:**
```bash
# Clone the repository
git clone <repository-url>
cd vslicer

# Install with uv (recommended)
uv pip install -e .

# Or with pip
pip install -e .
```

## Usage

### Basic Workflow

1. **Copy a video URL to clipboard** (optional)
2. **Launch VSlicer:**
   ```bash
   vslicer
   # or specify URL directly
   vslicer https://example.com/video.webm
   ```
3. **Navigate the video:**
   - Press `Space` to play/pause
   - Press `.` to step forward one frame
   - Press `,` to step backward one frame
4. **Mark your clip:**
   - Press `i` to mark the IN point (start)
   - Press `o` to mark the OUT point (end)
5. **Export:**
   - Press `e` to start export process
   - Choose output location and options
   - Optionally apply slow-motion

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play/Pause |
| `.` | Frame step forward |
| `,` | Frame step backward |
| `i` | Set IN point |
| `o` | Set OUT point |
| `e` | Export clip |
| `h` | Show help |
| `q` | Quit |

### GUI (Windows/Linux)

The GUI provides a complete visual interface with embedded video playback.

**Run (Linux/devcontainer):**
```bash
PYTHONPATH=src python -m vslicer_gui.app
```

**Run (Windows):**
```
windows_gui.bat
```

**GUI Features:**
- Embedded mpv video playback in the main window
- Seekbar with draggable IN (green) and OUT (red) markers
- Click-to-seek and drag-to-scrub
- Preview loop modes: Forward, Reverse, Ping-Pong
- Crop overlay for vertical video export
- Export dialog with resolution, slow-motion, and format options

**Crop Overlay:**
- Visual preview constrained to actual video bounds
- Drag inside rectangle to reposition
- Drag edges to resize (switches to custom mode)
- Darkened areas show what will be cropped out

Export honors the selected preview mode (reverse/ping-pong).

### Export Options

**Export Modes:**
- **Fast** - Stream copy (faster, less accurate, no slow-motion)
- **Accurate** - Re-encode with VP9 (slower, frame-accurate, supports filters)

**Slow Motion:**
- Specify a **factor** (e.g., 2.0 for 2x slower)
- Or specify **target duration** (e.g., stretch 2s to 10s)
- Audio options: stretch, mute, or auto-drop

**Crop for Vertical Video (GUI):**
- Enable "Crop for vertical" checkbox
- Choose preset aspect ratios: 9:16 (Reels/TikTok), 4:5 (Instagram), 1:1 (Square)
- Or drag edges of the crop rectangle for custom width
- Drag inside the rectangle to reposition
- Visual overlay shows exactly what will be exported

### Examples

**Simple clip extraction:**
```bash
# Copy URL to clipboard, then:
vslicer

# Or provide URL directly:
vslicer https://example.com/video.webm
```

**With debug logging:**
```bash
vslicer --debug
```

**Inspect resolved config:**
```bash
vslicer --print-config
```

## Configuration

VSlicer reads runtime settings from environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VSLICER_OUTPUT_DIR` | `./clips` | Default export directory |
| `VSLICER_MIN_DURATION` | `0.05` | Minimum clip duration (seconds) |
| `VSLICER_STRICT_WEBM` | `false` | Strict URL validation for `.webm` |
| `VSLICER_ENABLE_CROP` | `true` | Enable crop UI/filters |
| `VSLICER_LOG_LEVEL` | `INFO` | Log level |
| `VSLICER_LOG_FORMAT` | `text` | `text` or `json` |
| `VSLICER_LOG_FILE` | *(empty)* | Enable file logging when set |
| `VSLICER_LOG_MAX_SIZE_MB` | `10` | Log rotation size (MB) |
| `VSLICER_LOG_BACKUP_COUNT` | `3` | Log rotation backups |
| `VSLICER_LOG_RETENTION_DAYS` | `30` | Cleanup age for old logs |
| `VSLICER_FORCE_X11` | `false` | Force Qt to use X11 (`xcb`) |
| `VSLICER_ALLOWED_HOSTS` | *(empty)* | Comma-separated host allowlist |
| `VSLICER_BLOCKED_HOSTS` | *(empty)* | Comma-separated host denylist |
| `VSLICER_LOCAL_ONLY` | `false` | Restrict HTTP(S) to localhost |
| `VSLICER_YTDLP_TIMEOUT` | `60` | yt-dlp resolve timeout (seconds) |
| `VSLICER_FFMPEG_TIMEOUT` | `0` | ffmpeg timeout (seconds, 0 disables) |
| `VSLICER_FFPROBE_TIMEOUT` | `30` | ffprobe timeout (seconds) |
| `VSLICER_VALIDATE_REMOTE_MEDIA` | `false` | Use ffprobe to verify remote URLs |
| `VSLICER_ENABLE_COOKIE_FALLBACK` | `true` | Allow cookie-based retry for restricted media |
| `VSLICER_YTDLP_COOKIES_FROM_BROWSER` | `firefox` | Browser/profile for yt-dlp cookies |

For GUI media access prompts, VSlicer stores a user config file at:
- Linux: `~/.config/vslicer/config.json`
- macOS: `~/Library/Application Support/vslicer/config.json`
- Windows: `%LOCALAPPDATA%\\vslicer\\config.json`

The key `media_access_policy` can be set to `ask`, `allow`, or `deny` to reset
the "Don't show this again" choice.

VSlicer also reads an optional project-local `config.json` from the current
working directory. Example:

```json
{
  "cookies_from_browser": "firefox:[profile_id].default-release"
}
```

## How It Works

### Architecture

VSlicer uses a three-component architecture:

1. **mpv** - Handles video playback and frame-stepping via JSON IPC
2. **ffmpeg** - Processes and exports video clips with optional filters
3. **Python CLI** - Orchestrates the workflow with a user-friendly interface

### Technical Details

**Frame Stepping:**
- Uses mpv's `frame-step` and `frame-back-step` commands
- Provides visual frame accuracy (not guaranteed decoder frame index)

**Slow Motion:**
- Video: Uses ffmpeg's `setpts` filter
- Audio: Chains multiple `atempo` filters to work within [0.5, 2.0] limits
- Example: 5x slow-motion chains `atempo=0.5,atempo=0.5,atempo=0.8`

**Platform Compatibility:**
- Linux/WSL: Unix domain sockets for mpv IPC
- Windows: Named pipes for mpv IPC (via platform abstraction layer)

## Development

### Project Structure

```
vslicer/
  src/
    vslicer_core/
      config.py        # Configuration and feature flags
      clipboard.py     # Clipboard URL reading
      mpv/            # mpv integration
        ipc.py         # Platform abstraction (sockets/pipes)
        client.py      # JSON IPC client
        process.py     # Process lifecycle
      export/         # FFmpeg integration
        ffmpeg.py      # Command builder & runner (incl. crop, dimensions)
        filters.py     # Video/audio/crop filter builders
        progress.py    # Progress parsing
      domain/         # Core models
        models.py      # ClipSpec, ExportOptions, CropOptions, etc.
        validate.py    # Validation logic
      services/       # App-agnostic helpers
        playback.py    # Build clip specs
        export.py      # Run exports with validation
    vslicer_cli/
      main.py          # CLI entry point
      ui/             # Terminal UI
        prompts.py     # Input prompts
        status.py      # Status display
        controls.py    # Keyboard handling
    vslicer_gui/
      app.py           # GUI entry point
      main_window.py   # Main application window
      export_worker.py # Background export thread
      widgets/
        video_view.py  # Embedded mpv + crop overlay
        seek_slider.py # Seekbar with IN/OUT markers
      dialogs/
        export_dialog.py # Export options dialog
  tests/
    unit/            # Unit tests (71 tests)
    integration/     # Integration tests
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run filter tests (critical atempo chain algorithm)
uv run pytest tests/unit/test_filters.py -v

# Run with coverage
uv run pytest --cov=vslicer
```

### Development Setup

#### Rebuild anywhere (devcontainer)

1. Open the repo in VS Code with the Dev Containers extension.
2. Choose **Reopen in Container**.

The devcontainer installs system deps (mpv/ffmpeg + Qt runtime libs) and Python deps
via `/.devcontainer/postCreate.sh`.

```bash
# Install dev dependencies
uv sync

# Run linter
uv run ruff check src/

# Format code
uv run ruff format src/
```

## Troubleshooting

### mpv not found
- **Linux/WSL:** `sudo apt install mpv`
- **Windows:** Download from [mpv.io](https://mpv.io)
- **macOS:** `brew install mpv`

### ffmpeg not found
- **Linux/WSL:** `sudo apt install ffmpeg`
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org)
- **macOS:** `brew install ffmpeg`

### mpv IPC connection fails
- Ensure mpv is version 0.33.0 or later (includes IPC support)
- Check that no firewall is blocking Unix sockets (Linux) or named pipes (Windows)
- Try with `--debug` flag to see detailed error messages

### Export fails
- Check ffmpeg supports VP9: `ffmpeg -codecs | grep vp9`
- Check ffmpeg supports Opus: `ffmpeg -codecs | grep opus`
- Ensure output directory exists and is writable
- Try with accurate mode instead of fast mode

### Slow-motion audio issues
- Very high slow-motion factors (>10x) may not support audio stretching
- Use "mute audio" option for extreme slow-motion
- Check ffmpeg version supports atempo filter: `ffmpeg -filters | grep atempo`

## Known Limitations

1. **URL Support:** Works best with direct video URLs. Embedded players (YouTube, Vimeo) not supported.
2. **Frame Accuracy:** Visual frame accuracy only, not guaranteed to match exact decoder frame indices.
3. **Audio Limits:** Extreme slow-motion (>10x) may require muting audio due to atempo filter limits.
4. **Windows IPC:** Named pipe support on Windows may have edge cases; Linux/WSL is the primary development platform.

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass: `uv run pytest`
5. Submit a pull request

## License

[Add your license here]

## Acknowledgments

- **mpv** - Excellent media player with scriptable IPC
- **ffmpeg** - Powerful video processing framework
- **rich** - Beautiful terminal formatting library
