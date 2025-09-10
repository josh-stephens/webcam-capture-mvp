"""
Tests for the audio processing module.
"""

import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
import pytest
import numpy as np

from src.audio.processor import AudioProcessor


@pytest.mark.unit
class TestAudioProcessorInitialization:
    """Test audio processor initialization."""
    
    def test_audio_processor_creation(self, test_settings):
        """Test creating an audio processor with test settings."""
        processor = AudioProcessor(test_settings)
        
        assert processor.settings == test_settings
        assert not processor.is_running
        assert processor._whisper_model is None
        assert len(processor.activation_phrases) == 5
        
        # Check activation phrases are properly mapped
        expected_phrases = test_settings.activation.phrases
        for key, phrase in expected_phrases.items():
            assert phrase in processor.activation_phrases
            
    def test_audio_buffer_initialization(self, test_settings):
        """Test audio buffer is properly initialized."""
        processor = AudioProcessor(test_settings)
        
        expected_maxlen = (
            test_settings.audio.buffer_duration_sec * 
            test_settings.audio.sample_rate
        )
        assert processor.audio_buffer.maxlen == expected_maxlen
        assert len(processor.audio_buffer) == 0
        assert len(processor.voice_segments) == 0


@pytest.mark.unit
class TestAudioProcessorLifecycle:
    """Test audio processor lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_start_audio_processor(self, test_settings):
        """Test starting the audio processor."""
        processor = AudioProcessor(test_settings)
        
        # Mock VAD and Whisper initialization
        processor.vad.initialize = AsyncMock()
        processor._load_whisper_model = AsyncMock()
        
        await processor.start()
        
        assert processor.is_running
        processor.vad.initialize.assert_called_once()
        processor._load_whisper_model.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_stop_audio_processor(self, test_settings):
        """Test stopping the audio processor."""
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        processor.vad.cleanup = AsyncMock()
        
        await processor.stop()
        
        assert not processor.is_running
        processor.vad.cleanup.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_start_already_running(self, test_settings):
        """Test starting an already running processor."""
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        
        processor.vad.initialize = AsyncMock()
        processor._load_whisper_model = AsyncMock()
        
        await processor.start()
        
        # Should not call initialization again
        processor.vad.initialize.assert_not_called()
        processor._load_whisper_model.assert_not_called()


@pytest.mark.unit  
class TestAudioChunkProcessing:
    """Test audio chunk processing functionality."""
    
    @pytest.mark.asyncio
    async def test_process_audio_chunk_not_running(self, test_settings, sample_audio_bytes):
        """Test processing chunk when processor is not running."""
        processor = AudioProcessor(test_settings)
        timestamp = time.time()
        
        # Should return early without processing
        await processor.process_chunk(sample_audio_bytes, timestamp)
        
        # Buffer should remain empty
        assert len(processor.audio_buffer) == 0
        assert processor.stats["chunks_processed"] == 0
        
    @pytest.mark.asyncio
    async def test_process_audio_chunk_with_voice(self, test_settings, sample_audio_bytes):
        """Test processing audio chunk containing voice."""
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        
        # Mock VAD to detect voice
        processor.vad.detect_voice_activity = AsyncMock(return_value=True)
        processor._handle_voice_detected = AsyncMock()
        
        timestamp = time.time()
        await processor.process_chunk(sample_audio_bytes, timestamp)
        
        # Should have processed the chunk
        assert processor.stats["chunks_processed"] == 1
        assert processor.stats["processing_time_total"] > 0
        
        # Should have called voice handler
        processor._handle_voice_detected.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_process_audio_chunk_with_silence(self, test_settings, silent_audio_bytes):
        """Test processing audio chunk containing silence."""
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        
        # Mock VAD to detect silence
        processor.vad.detect_voice_activity = AsyncMock(return_value=False)
        processor._handle_silence_detected = AsyncMock()
        
        timestamp = time.time()
        await processor.process_chunk(silent_audio_bytes, timestamp)
        
        # Should have processed the chunk
        assert processor.stats["chunks_processed"] == 1
        
        # Should have called silence handler
        processor._handle_silence_detected.assert_called_once()


@pytest.mark.unit
class TestVoiceDetectionHandling:
    """Test voice detection and segment management."""
    
    @pytest.mark.asyncio
    async def test_handle_voice_detected(self, test_settings, sample_audio_data):
        """Test handling detected voice activity."""
        processor = AudioProcessor(test_settings)
        processor._check_for_activation_phrases = AsyncMock()
        
        timestamp = time.time()
        
        # Process voice segments
        await processor._handle_voice_detected(sample_audio_data, timestamp)
        await processor._handle_voice_detected(sample_audio_data, timestamp + 1)
        await processor._handle_voice_detected(sample_audio_data, timestamp + 2)
        
        # Should have added voice segments
        assert len(processor.voice_segments) == 3
        assert processor.stats["voice_segments_detected"] == 3
        
        # Should check for activation phrases
        processor._check_for_activation_phrases.assert_called()
        
    @pytest.mark.asyncio
    async def test_voice_segment_expiration(self, test_settings, sample_audio_data):
        """Test that old voice segments are removed."""
        processor = AudioProcessor(test_settings)
        processor._check_for_activation_phrases = AsyncMock()
        
        old_timestamp = time.time() - 15  # 15 seconds ago
        new_timestamp = time.time()
        
        # Add old segment
        await processor._handle_voice_detected(sample_audio_data, old_timestamp)
        
        # Add new segment - should remove old one
        await processor._handle_voice_detected(sample_audio_data, new_timestamp)
        
        # Should only have the new segment (old one expired)
        assert len(processor.voice_segments) == 1
        assert processor.voice_segments[0]["timestamp"] == new_timestamp


@pytest.mark.unit
class TestVoiceActivationPhrases:
    """Test voice activation phrase detection."""
    
    @pytest.mark.asyncio
    @patch('whisper.load_model')
    async def test_whisper_model_loading(self, mock_load_model, test_settings, mock_whisper_model):
        """Test Whisper model loading."""
        mock_load_model.return_value = mock_whisper_model
        
        processor = AudioProcessor(test_settings)
        await processor._load_whisper_model()
        
        assert processor._whisper_model == mock_whisper_model
        mock_load_model.assert_called_once_with(test_settings.audio.whisper_model)
        
    @pytest.mark.asyncio
    async def test_transcribe_audio(self, test_settings, mock_whisper_model, sample_audio_data):
        """Test audio transcription."""
        processor = AudioProcessor(test_settings)
        processor._whisper_model = mock_whisper_model
        
        result = await processor._transcribe_audio(sample_audio_data)
        
        assert result == "test transcription result"
        mock_whisper_model.transcribe.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_transcribe_audio_no_model(self, test_settings, sample_audio_data):
        """Test transcription when no model is loaded."""
        processor = AudioProcessor(test_settings)
        
        result = await processor._transcribe_audio(sample_audio_data)
        
        assert result is None
        
    @pytest.mark.asyncio
    async def test_activation_phrase_detection(self, test_settings, mock_whisper_model, sample_audio_data):
        """Test detection of activation phrases."""
        processor = AudioProcessor(test_settings)
        processor._whisper_model = mock_whisper_model
        processor.vault_writer.write_transcription = AsyncMock()
        
        # Mock handler methods
        processor._handle_start_recording = AsyncMock()
        
        # Mock transcription result containing activation phrase
        mock_whisper_model.transcribe.return_value = {
            "text": "test start recording please",
            "segments": []
        }
        
        # Add voice segments
        for i in range(5):
            processor.voice_segments.append({
                "audio": sample_audio_data,
                "timestamp": time.time() + i,
                "duration": 1.0
            })
            
        await processor._check_for_activation_phrases()
        
        # Should have detected activation and called handler
        processor._handle_start_recording.assert_called_once()
        processor.vault_writer.write_transcription.assert_called_once()
        
        # Check transcription was logged correctly
        call_args = processor.vault_writer.write_transcription.call_args
        assert call_args[1]["is_activation"] is True
        assert call_args[1]["activation_command"] == "test start recording"


@pytest.mark.unit
class TestActivationHandlers:
    """Test voice activation command handlers."""
    
    @pytest.mark.asyncio
    async def test_start_recording_handler(self, test_settings):
        """Test start recording activation handler."""
        processor = AudioProcessor(test_settings)
        
        # Should not raise any exceptions
        await processor._handle_start_recording()
        
    @pytest.mark.asyncio
    async def test_mark_important_handler(self, test_settings):
        """Test mark important activation handler."""
        processor = AudioProcessor(test_settings)
        
        # Should not raise any exceptions
        await processor._handle_mark_important()
        
    @pytest.mark.asyncio
    async def test_show_status_handler(self, test_settings, capsys):
        """Test show status activation handler."""
        processor = AudioProcessor(test_settings)
        
        await processor._handle_show_status()
        
        # Should print status to stdout
        captured = capsys.readouterr()
        assert "System Status:" in captured.out


@pytest.mark.unit
class TestAudioProcessorStatus:
    """Test audio processor status and metrics."""
    
    def test_get_status_not_running(self, test_settings):
        """Test getting status when processor is not running."""
        processor = AudioProcessor(test_settings)
        
        status = processor.get_status()
        
        assert status["is_running"] is False
        assert status["buffer_size"] == 0
        assert status["whisper_model_loaded"] is False
        assert status["stats"]["chunks_processed"] == 0
        
    def test_get_status_with_stats(self, test_settings):
        """Test getting status with processing statistics."""
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        processor.stats = {
            "chunks_processed": 100,
            "voice_segments_detected": 50,
            "activations_detected": 5,
            "processing_time_total": 1.5
        }
        
        status = processor.get_status()
        
        assert status["is_running"] is True
        assert status["stats"]["chunks_processed"] == 100
        assert status["stats"]["voice_segments_detected"] == 50
        assert status["stats"]["activations_detected"] == 5
        assert status["stats"]["avg_processing_time_ms"] == 15.0  # 1.5s / 100 chunks * 1000ms
        
    def test_custom_activation_phrase_management(self, test_settings):
        """Test adding and removing custom activation phrases."""
        processor = AudioProcessor(test_settings)
        
        # Add custom phrase
        custom_handler = AsyncMock()
        processor.add_custom_activation_phrase("custom phrase", custom_handler)
        
        assert "custom phrase" in processor.activation_phrases
        assert processor.activation_phrases["custom phrase"] == custom_handler
        
        # Remove phrase
        processor.remove_activation_phrase("custom phrase")
        
        assert "custom phrase" not in processor.activation_phrases