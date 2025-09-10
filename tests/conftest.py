"""
Test configuration and fixtures for the webcam capture MVP.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Generator, AsyncGenerator
import pytest
import numpy as np

from src.main import Settings, CaptureSettings, StorageSettings, AudioSettings, ActivationSettings, SystemSettings


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_dir: Path) -> Settings:
    """Create test settings with temporary directories."""
    return Settings(
        capture=CaptureSettings(
            video_device="Test Video Device",
            audio_device="Test Audio Device", 
            quality="low",
            frame_rate=15,
            resolution="640x480"
        ),
        storage=StorageSettings(
            archive_path=str(temp_dir / "archive"),
            max_daily_size_gb=1,
            retention_days=1,
            hot_storage_hours=1,
            warm_storage_days=1,
            cold_storage_years=1,
            enable_pruning=True,
            prune_silence_after_hours=1,
            prune_routine_after_days=1,
            keep_voice_segments=True
        ),
        audio=AudioSettings(
            vad_threshold=0.5,
            vad_model="webrtc",  # Use webrtc for testing as it's lighter
            whisper_model="tiny",  # Use smallest model for testing
            whisper_device="cpu",
            buffer_duration_sec=5,  # Smaller buffer for tests
            chunk_duration_sec=1,
            sample_rate=16000,
            channels=1
        ),
        activation=ActivationSettings(
            enabled=True,
            phrases={
                "start_recording": "test start recording",
                "mark_important": "test mark important",
                "analyze_content": "test analyze this",
                "show_status": "test show status",
                "pause_recording": "test pause recording"
            },
            confidence_threshold=0.5,  # Lower threshold for testing
            response_timeout_sec=1,
            cooldown_sec=0.1  # Faster cooldown for testing
        ),
        system=SystemSettings(
            log_level="DEBUG",
            log_format="text",
            log_file=str(temp_dir / "test.log"),
            max_cpu_percent=50,
            max_memory_gb=2,
            health_check_interval_sec=5,
            restart_on_failure=False,  # Don't restart during tests
            max_restart_attempts=1,
            restart_delay_sec=1
        )
    )


@pytest.fixture
def sample_audio_data() -> np.ndarray:
    """Generate sample audio data for testing."""
    # Generate 1 second of 16kHz audio (sine wave)
    sample_rate = 16000
    duration = 1.0
    frequency = 440  # A4 note
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    audio = np.sin(2 * np.pi * frequency * t)
    
    # Convert to int16 format (typical for audio processing)
    audio_int16 = (audio * 32767).astype(np.int16)
    return audio_int16


@pytest.fixture
def sample_audio_bytes(sample_audio_data: np.ndarray) -> bytes:
    """Convert sample audio data to bytes."""
    return sample_audio_data.tobytes()


@pytest.fixture
def silent_audio_data() -> np.ndarray:
    """Generate silent audio data for testing."""
    sample_rate = 16000
    duration = 1.0
    samples = int(sample_rate * duration)
    return np.zeros(samples, dtype=np.int16)


@pytest.fixture
def silent_audio_bytes(silent_audio_data: np.ndarray) -> bytes:
    """Convert silent audio data to bytes."""
    return silent_audio_data.tobytes()


@pytest.fixture
async def storage_manager(test_settings: Settings):
    """Create and start a storage manager for testing."""
    from src.storage.manager import StorageManager
    
    manager = StorageManager(test_settings)
    await manager.start()
    
    yield manager
    
    await manager.stop()


@pytest.fixture
async def audio_processor(test_settings: Settings):
    """Create an audio processor for testing (without starting)."""
    from src.audio.processor import AudioProcessor
    
    processor = AudioProcessor(test_settings)
    
    yield processor
    
    if processor.is_running:
        await processor.stop()


@pytest.fixture
async def vault_writer(test_settings: Settings):
    """Create a vault writer for testing."""
    from src.vault.writer import VaultWriter
    
    # Override vault path to use temp directory
    writer = VaultWriter(test_settings)
    writer.vault_path = Path(test_settings.storage.archive_path) / "vault"
    writer.daily_notes_path = writer.vault_path / "Logs" / "Daily"
    writer.transcription_notes_path = writer.vault_path / "Logs" / "Transcriptions"
    
    # Ensure directories exist
    writer.daily_notes_path.mkdir(parents=True, exist_ok=True)
    writer.transcription_notes_path.mkdir(parents=True, exist_ok=True)
    
    yield writer


@pytest.fixture  
def mock_ffmpeg_process():
    """Mock FFmpeg process for testing."""
    from unittest.mock import Mock, MagicMock
    
    process = Mock()
    process.stdout = MagicMock()
    process.stderr = MagicMock()
    process.poll.return_value = None  # Process is running
    process.terminate = MagicMock()
    process.kill = MagicMock()
    process.wait = MagicMock()
    process.returncode = 0
    
    return process


@pytest.fixture
def mock_whisper_model():
    """Mock Whisper model for testing."""
    from unittest.mock import Mock
    
    model = Mock()
    model.transcribe.return_value = {
        "text": "test transcription result",
        "segments": []
    }
    
    return model


class AudioStreamMock:
    """Mock audio stream for testing."""
    
    def __init__(self, audio_data: bytes, chunk_size: int = 1024):
        self.data = audio_data
        self.chunk_size = chunk_size
        self.position = 0
        
    def read(self, size: int = None) -> bytes:
        """Read chunk from mock audio stream."""
        if size is None:
            size = self.chunk_size
            
        if self.position >= len(self.data):
            return b""  # End of stream
            
        chunk = self.data[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


@pytest.fixture
def audio_stream_mock(sample_audio_bytes: bytes):
    """Create a mock audio stream with sample data."""
    return AudioStreamMock(sample_audio_bytes)


# Test markers for different test categories
pytest.mark.unit = pytest.mark.unit
pytest.mark.integration = pytest.mark.integration  
pytest.mark.performance = pytest.mark.performance
pytest.mark.hardware = pytest.mark.hardware