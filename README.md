# Webcam Capture MVP

The foundational sensor module for the Personal Automation System, providing continuous audio/video capture with voice activation, intelligent content management, and automatic transcription logging to Obsidian vault.

## 🚀 Current Status: Development Ready

**Phase**: Foundation implementation with vault integration complete  
**Implementation**: Core architecture and vault logging system built  
**Next**: Begin actual capture pipeline development  

## Quick Start

```powershell
# Setup environment
cd C:\Users\josh\Projects\syl\code\personal-automation\webcam-capture
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Install FFmpeg (required for capture)
winget install FFmpeg

# Run the capture system
python src\main.py
```

## 🎯 Core Features Implemented

### Voice Transcription & Vault Integration
- **Daily Note Creation**: Automatic daily notes in `Ours/Logs/Daily/`
- **Real-time Logging**: All voice transcriptions logged with timestamps
- **Voice Activation Tracking**: Special formatting for activation commands
- **System Event Logging**: Startup, shutdown, errors logged to vault
- **Summary Generation**: Daily transcription summaries with analysis

### Voice Activation Commands
- `"Computer, start recording"` → High-quality capture mode
- `"Computer, mark important"` → Flag content as permanent retention
- `"Computer, analyze this"` → Trigger deep content analysis
- `"Computer, show status"` → Display system health metrics
- `"Computer, pause recording"` → Temporary capture suspension

### Architecture Foundation
- **Async-first Design**: Real-time processing with asyncio
- **Dual-stream Capture**: Video archive + audio processing pipeline
- **Three-tier Storage**: Hot/warm/cold storage with intelligent pruning
- **Voice Activity Detection**: Silero VAD + WebRTC VAD support
- **Local Speech Recognition**: Whisper integration for privacy

## Documentation

Complete documentation is available in the Obsidian vault:
- [MVP Specification](../../../Ours/Projects/Personal-Automation-System/MVP-Webcam-Capture.md)
- [Architecture Overview](../../../Ours/Projects/Personal-Automation-System/Architecture.md)
- [Technology Stack](../../../Ours/Knowledge/Tech-Stack.md)
- [Development Instructions](CLAUDE.md)
- [Implementation Tasks](TASKS.md)
- [Product Requirements](PRD-MVP.md)

## 📁 Project Structure

```
webcam-capture/
├── src/
│   ├── main.py              # Application entry point
│   ├── capture/             # FFmpeg-based video capture
│   │   └── webcam_capture.py
│   ├── audio/              # Real-time audio processing
│   │   ├── processor.py    # Audio analysis & voice activation
│   │   └── vad.py         # Voice Activity Detection
│   ├── storage/           # Three-tier storage management
│   │   └── manager.py
│   └── vault/             # Obsidian vault integration
│       └── writer.py
├── config/
│   ├── default.yaml       # Default configuration
│   └── .env.example      # Environment variables template
├── tests/                 # Test suite (to be implemented)
├── CLAUDE.md             # Development instructions
├── TASKS.md              # Implementation roadmap
├── PRD-MVP.md            # Product requirements
└── requirements.txt      # Python dependencies
```

## 🔧 Technical Implementation Status

### ✅ Completed Components
- **Main Application**: Async orchestration with proper shutdown handling
- **Audio Processor**: Voice detection, transcription, and activation phrase routing
- **Voice Activity Detection**: Silero VAD and WebRTC VAD implementations
- **Storage Manager**: Three-tier storage with intelligent pruning logic
- **Vault Writer**: Obsidian integration with daily note automation
- **Configuration**: YAML config with environment variable overrides

### 🚧 Ready for Implementation
- **Webcam Capture**: FFmpeg integration (structure complete, needs implementation)
- **Testing Suite**: Unit and integration tests (framework ready)
- **API Endpoints**: RESTful API for status and control (planned)
- **Agent Communication**: Syl orchestrator integration (interfaces defined)

## Voice Commands

- `"Computer, start recording"` - High-quality capture mode
- `"Computer, mark important"` - Flag recent content as permanent
- `"Computer, analyze this"` - Process recent audio/video
- `"Computer, show status"` - Display system health
- `"Computer, pause recording"` - Temporary suspension

## Configuration

Configuration is managed through environment variables and config files:

```bash
# .env file
WEBCAM_DEVICE="USB Camera"
AUDIO_DEVICE="Microphone"
ARCHIVE_PATH="C:\archive"
PROCESSING_ENABLED=true
```

## Development

```powershell
# Install development dependencies
pip install -r requirements.txt

# Run tests
pytest

# Code formatting
black src tests
isort src tests

# Type checking
mypy src
```

## Integration

This module integrates with:
- **Syl Orchestrator**: System coordination and task management
- **Vault Curator**: Documentation and knowledge management
- **Storage System**: Three-tier archival strategy
- **Audio Processor**: Real-time voice analysis

## Status

**Current Phase**: Planning and Architecture  
**Next Milestone**: Basic capture implementation  
**Target**: MVP deployment within 2-3 weeks

For detailed development progress, see [Todo.md](../../../Ours/Todo.md).