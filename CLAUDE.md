# Webcam Capture MVP - Claude Code Instructions

*Project: Personal Automation System | Module: Webcam Capture | Version: 1.0*

## Project Overview

This is the foundational MVP for a personal automation system that provides continuous webcam capture with voice activation and intelligent content management. This module establishes the core patterns for all future sensor integrations in the broader consciousness scaffolding system.

## Development Context

### Core Philosophy
- **Privacy First**: All processing must be local, no cloud dependencies for core functionality
- **Continuous Operation**: System must run 24/7 with automatic recovery
- **Intelligence at Edge**: Real-time processing with minimal latency
- **Human Agency**: User maintains complete control and override capability
- **Modular Design**: Clean interfaces for integration with other system components

### System Architecture
```
USB Webcam → FFmpeg Capture → Dual Output:
├── Video Stream → Archive Storage (Full Quality)
└── Audio Stream → VAD → Buffer → Whisper → Action Router
```

## Technical Constraints

### Platform Requirements
- **OS**: Windows (primary) with PowerShell automation
- **Python**: 3.11+ with asyncio for real-time processing
- **Hardware**: USB webcam, 8GB+ RAM, 100GB+ storage
- **Dependencies**: FFmpeg, OpenCV, Whisper, Silero VAD

### Performance Requirements
- **Capture**: 24/7 operation with <1% downtime
- **Response Time**: Voice activation within 2 seconds
- **Storage**: Intelligent pruning to maintain <10GB/day
- **Recovery**: Automatic restart from any failure mode

### Security Requirements
- **Local Processing**: No external API calls for core functionality
- **Access Control**: File permissions and secure storage
- **Audit Trail**: Complete logging of all system actions
- **Privacy**: User-controlled data retention and deletion

## Code Style Guidelines

### Python Standards
```python
# Use type hints for all functions
def process_audio(chunk: bytes, timestamp: float) -> AudioResult:
    """Process audio chunk with timestamp."""
    pass

# Async/await for I/O operations
async def capture_stream() -> AsyncGenerator[bytes, None]:
    """Async generator for audio stream."""
    pass

# Structured logging
import structlog
logger = structlog.get_logger()
logger.info("Processing started", chunk_size=len(chunk))
```

### Vault Integration Patterns
```python
# Always log transcriptions with metadata
await self.vault_writer.write_transcription(
    text=transcribed_text,
    timestamp=datetime.now(),
    confidence=whisper_confidence,
    is_activation=is_voice_command,
    activation_command=matched_phrase
)

# Log system events for audit trail
await self.vault_writer.write_system_event(
    event_type="startup|shutdown|error|warning",
    description="Human-readable description",
    metadata={"key": "value"}  # Optional context
)
```

### Architecture Patterns
- **Dependency Injection**: Use dependency injection for testability
- **Event-Driven**: Async events for real-time processing
- **Error Handling**: Graceful degradation with automatic recovery
- **Configuration**: YAML files with environment variable overrides

### File Organization
```
src/
├── main.py          # Application entry point and orchestration
├── capture/         # Core capture functionality
│   └── webcam_capture.py    # FFmpeg-based dual-stream capture
├── audio/           # Audio processing pipeline
│   ├── processor.py         # Real-time analysis & voice activation
│   └── vad.py              # Voice Activity Detection (Silero/WebRTC)
├── storage/         # Storage management
│   └── manager.py          # Three-tier storage with intelligent pruning
├── vault/           # Obsidian vault integration
│   └── writer.py           # Daily note creation and transcription logging
└── config/          # Configuration management
    └── default.yaml        # YAML configuration with env overrides
```

## Implementation Requirements

### Core Components

#### 1. Webcam Capture (capture/webcam_capture.py)
```python
class WebcamCapture:
    """Continuous webcam capture with dual output streams."""
    
    async def start_capture(self) -> None:
        """Start continuous recording with FFmpeg."""
        
    async def stop_capture(self) -> None:
        """Gracefully stop recording."""
        
    def get_health_status(self) -> Dict[str, Any]:
        """Return system health metrics."""
```

#### 2. Audio Processing (audio/processor.py)
```python
class AudioProcessor:
    """Real-time audio analysis and voice activation."""
    
    async def process_stream(self, audio_stream: AsyncGenerator) -> None:
        """Process continuous audio stream."""
        
    def detect_activation(self, audio_chunk: bytes) -> Optional[str]:
        """Detect voice activation phrases."""
        
    def mark_for_pruning(self, timestamp: float) -> None:
        """Mark audio segment for later pruning."""
```

#### 3. Storage Management (storage/manager.py)
```python
class StorageManager:
    """Three-tier storage with intelligent pruning."""
    
    async def store_video(self, video_data: bytes, metadata: Dict) -> str:
        """Store video with metadata tagging."""
        
    async def prune_old_content(self) -> None:
        """Apply retention policies and pruning rules."""
        
    def get_storage_metrics(self) -> Dict[str, Any]:
        """Return storage usage and health metrics."""
```

#### 4. Vault Integration (vault/writer.py)
```python
class VaultWriter:
    """Handles writing transcriptions to Obsidian vault."""
    
    async def write_transcription(self, text: str, timestamp: datetime, 
                                confidence: float, is_activation: bool,
                                activation_command: Optional[str]) -> None:
        """Write transcription to daily note."""
        
    async def write_system_event(self, event_type: str, description: str,
                               timestamp: Optional[datetime],
                               metadata: Optional[Dict]) -> None:
        """Write system event to daily note."""
        
    async def create_transcription_summary(self, date_filter: Optional[date]) -> None:
        """Create summary of transcriptions for analysis."""
```

### Voice Activation System

#### Activation Phrases
```python
ACTIVATION_PHRASES = {
    "computer start recording": "start_high_quality_mode",
    "computer mark important": "mark_permanent_keep", 
    "computer analyze this": "analyze_recent_content",
    "computer show status": "display_system_status",
    "computer pause recording": "pause_capture_temporarily"
}
```

#### Action Handlers
```python
class ActionHandler:
    """Execute actions triggered by voice commands."""
    
    async def start_high_quality_mode(self) -> None:
        """Switch to high-quality capture settings."""
        
    async def mark_permanent_keep(self) -> None:
        """Flag last 5 minutes as permanent retention."""
        
    async def analyze_recent_content(self) -> None:
        """Run deep analysis on recent audio/video."""
```

## Testing Requirements

### Unit Tests
- Test each component in isolation
- Mock external dependencies (FFmpeg, hardware)
- Test error conditions and edge cases
- Verify async behavior and timing

### Integration Tests
- End-to-end capture pipeline
- Voice activation flow
- Storage and pruning operations
- Agent communication protocols

### Performance Tests
- 24-hour continuous operation
- Memory usage and leak detection
- Storage growth rate validation
- Response time measurements

## Configuration Management

### Environment Variables
```bash
# .env file
WEBCAM_DEVICE="USB Camera"
AUDIO_DEVICE="Microphone"
ARCHIVE_PATH="C:\archive"
LOG_LEVEL="INFO"
WHISPER_MODEL="base"
VAD_THRESHOLD=0.5
```

### Configuration Schema
```yaml
# config/default.yaml
capture:
  video_device: "USB Camera"
  audio_device: "Microphone"
  quality: "medium"
  
storage:
  archive_path: "C:\\archive"
  max_daily_size_gb: 10
  retention_days: 30
  
audio:
  vad_threshold: 0.5
  whisper_model: "base"
  buffer_duration_sec: 30
```

## Integration Points

### Syl Orchestrator Communication
```python
class SylClient:
    """Communication interface with Syl orchestrator."""
    
    async def report_status(self, status: SystemStatus) -> None:
        """Send health and performance metrics."""
        
    async def receive_commands(self) -> AsyncGenerator[Command, None]:
        """Listen for commands from orchestrator."""
        
    async def send_alert(self, alert: Alert) -> None:
        """Send critical alerts and notifications."""
```

### Knowledge Vault Integration
- Auto-update documentation based on system performance
- Log decisions and pattern discoveries
- Contribute insights to shared knowledge base
- Maintain audit trail of all activities

## Deployment Guidelines

### Development Setup
```powershell
# Setup development environment
cd C:\Users\josh\Projects\syl\code\personal-automation\webcam-capture
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Install FFmpeg
winget install FFmpeg

# Run tests
pytest tests/

# Start development server
python src/main.py --config config/development.yaml
```

### Production Deployment
- Use Windows Service for continuous operation
- Implement health checks and automatic restart
- Set up monitoring and alerting
- Configure log rotation and archival

## Error Handling and Recovery

### Failure Modes
- USB device disconnection
- Disk space exhaustion
- Process crashes or hangs
- Network connectivity issues

### Recovery Strategies
- Automatic device re-detection
- Emergency storage cleanup
- Process restart with state recovery
- Graceful degradation to basic operation

## Performance Monitoring

### Key Metrics
- Capture uptime percentage
- Audio processing latency
- Storage usage trends
- Voice activation accuracy
- System resource utilization

### Alerting Conditions
- Capture downtime > 1 minute
- Storage usage > 90%
- Processing latency > 5 seconds
- Voice activation accuracy < 90%

## Future Integration Points

### Module 2: Sensor Discovery
- Register webcam capabilities
- Report health and performance metrics
- Participate in coordinated sensor management

### Module 3: Data Pipeline
- Stream processed data to central store
- Contribute to cross-modal analysis
- Share insights with other modules

### Module 4: Location Intelligence
- Correlate capture events with location data
- Adjust capture behavior based on context
- Contribute environmental awareness

## Development Notes

### Current Status
- **Phase**: Initial implementation
- **Next Milestone**: Basic capture pipeline working
- **Estimated Completion**: 2-3 weeks

### Key Decisions Made
- FFmpeg chosen over OBS for reliability
- Silero VAD selected for performance
- Asyncio architecture for real-time processing
- YAML configuration for flexibility

### Open Questions
- Optimal buffer sizes for real-time processing
- Balance between quality and storage efficiency
- Integration patterns with future modules
- Performance tuning for extended operation

---

*This document serves as the primary reference for all development work on the webcam capture MVP. Update this file as architectural decisions are made and implementation progresses.*

**Last Updated**: 2025-01-09  
**Next Review**: Weekly during active development  
**Owner**: Josh & Syl Orchestrator