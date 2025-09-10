"""
End-to-End Integration Tests

Tests the complete webcam capture pipeline from device detection 
through audio processing and vault integration.
"""

import asyncio
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import pytest

from src.main import WebcamCaptureApp, Settings
from src.utils.device_detection import DeviceDetector, DeviceType


@pytest.mark.integration
class TestEndToEndPipeline:
    """Test the complete capture pipeline integration."""
    
    @pytest.mark.asyncio
    async def test_app_initialization_and_startup(self, test_settings):
        """Test complete application initialization and startup sequence."""
        app = WebcamCaptureApp(test_settings)
        
        # Mock external dependencies
        app.storage_manager.start = AsyncMock()
        app.audio_processor.start = AsyncMock()
        app.audio_processor.vault_writer.write_system_event = AsyncMock()
        app.webcam_capture.start = AsyncMock()
        
        # Mock shutdown event to exit quickly
        app.shutdown_event.set()
        
        try:
            await app.start()
            
            # Verify initialization sequence
            app.storage_manager.start.assert_called_once()
            app.audio_processor.start.assert_called_once()
            app.audio_processor.vault_writer.write_system_event.assert_called_once()
            app.webcam_capture.start.assert_called_once()
            
            # Check system event logging
            call_args = app.audio_processor.vault_writer.write_system_event.call_args
            assert call_args[1]["event_type"] == "startup"
            assert call_args[1]["description"] == "Webcam capture system started successfully"
            
        finally:
            await app.stop()
    
    @pytest.mark.asyncio
    async def test_audio_processing_pipeline(self, test_settings, sample_audio_bytes):
        """Test the complete audio processing pipeline."""
        from src.audio.processor import AudioProcessor
        
        processor = AudioProcessor(test_settings)
        
        # Mock dependencies
        processor.vad.initialize = AsyncMock()
        processor.vad.detect_voice_activity = AsyncMock(return_value=True)
        processor.vad.cleanup = AsyncMock()
        processor._load_whisper_model = AsyncMock()
        processor._whisper_model = Mock()
        processor._whisper_model.transcribe.return_value = {
            "text": "test transcription",
            "segments": []
        }
        processor.vault_writer.write_transcription = AsyncMock()
        
        try:
            # Start processor
            await processor.start()
            assert processor.is_running
            
            # Process audio chunks
            timestamp = time.time()
            await processor.process_chunk(sample_audio_bytes, timestamp)
            
            # Verify processing occurred
            assert processor.stats["chunks_processed"] == 1
            processor.vad.detect_voice_activity.assert_called_once()
            
            # Add enough voice segments to trigger transcription
            for i in range(5):
                await processor.process_chunk(sample_audio_bytes, timestamp + i)
                
            # Should have triggered activation phrase checking
            processor.vault_writer.write_transcription.assert_called()
            
        finally:
            await processor.stop()
            assert not processor.is_running
    
    @pytest.mark.asyncio
    async def test_webcam_capture_with_mocked_ffmpeg(self, test_settings, sample_audio_bytes):
        """Test webcam capture with mocked FFmpeg process."""
        from src.capture.webcam_capture import WebcamCapture
        
        audio_processor = Mock()
        audio_processor.process_chunk = AsyncMock()
        
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Mock FFmpeg process
        mock_process = Mock()
        mock_stdout = Mock()
        
        # Create audio stream simulation
        audio_chunks = [sample_audio_bytes[i:i+1024] for i in range(0, len(sample_audio_bytes), 1024)]
        audio_chunks.append(b"")  # End of stream
        
        mock_stdout.read.side_effect = audio_chunks
        mock_process.stdout = mock_stdout
        mock_process.stderr = Mock()
        mock_process.poll.return_value = None  # Process is running
        mock_process.terminate = Mock()
        mock_process.kill = Mock()
        mock_process.wait = Mock()
        
        with patch('src.capture.webcam_capture.subprocess.Popen', return_value=mock_process):
            try:
                await capture.start()
                
                # Verify capture started
                assert capture.is_recording
                assert capture.process == mock_process
                
                # Allow some processing time
                await asyncio.sleep(0.1)
                
                # Verify audio processing was called
                audio_processor.process_chunk.assert_called()
                
            finally:
                await capture.stop()
                assert not capture.is_recording
    
    @pytest.mark.asyncio
    async def test_vault_integration_workflow(self, test_settings, vault_writer):
        """Test the complete vault integration workflow."""
        from datetime import datetime
        
        # Test system event logging
        await vault_writer.write_system_event(
            event_type="startup",
            description="Test system startup",
            metadata={"test": "value"}
        )
        
        # Test transcription logging
        await vault_writer.write_transcription(
            text="Hello world",
            timestamp=datetime.now(),
            confidence=0.95,
            is_activation=True,
            activation_command="test start recording"
        )
        
        # Verify daily note was created
        today = datetime.now().date()
        daily_note_path = vault_writer.daily_notes_path / f"{today}.md"
        
        assert daily_note_path.exists()
        
        # Check content
        content = daily_note_path.read_text()
        assert "Hello world" in content
        assert "test start recording" in content
        assert "Test system startup" in content
        
        # Test summary generation
        await vault_writer.create_transcription_summary()
        
        # Verify stats were updated
        assert vault_writer.stats["transcriptions_written"] > 0
        assert vault_writer.stats["voice_activations_logged"] > 0
    
    @pytest.mark.asyncio
    async def test_storage_manager_integration(self, test_settings, storage_manager):
        """Test storage manager with three-tier architecture."""
        
        # Test video storage
        test_video_data = b"fake video data" * 1000
        metadata = {
            "timestamp": time.time(),
            "device": "Test Camera",
            "resolution": "640x480",
            "fps": 15
        }
        
        file_path = await storage_manager.store_video(test_video_data, metadata)
        
        # Verify file was stored in hot storage
        assert file_path.exists()
        assert file_path.parent == storage_manager.hot_storage
        
        # Test metadata storage
        metadata_file = storage_manager.metadata_path / f"{file_path.stem}.json"
        assert metadata_file.exists()
        
        # Test storage metrics
        metrics = storage_manager.get_storage_metrics()
        assert metrics["total_files"] > 0
        assert metrics["hot_storage_usage"] > 0
        
        # Test pruning simulation
        await storage_manager.prune_old_content()
        
        # Should not error even with recent files
        assert file_path.exists()  # Still too recent to prune


@pytest.mark.integration 
class TestDeviceDetectionIntegration:
    """Test device detection integration with the capture system."""
    
    @pytest.mark.asyncio
    async def test_device_discovery_workflow(self):
        """Test the complete device discovery workflow."""
        detector = DeviceDetector()
        
        # Test discovery (will fail without actual devices, but should not crash)
        devices = await detector.discover_devices(DeviceType.BOTH)
        
        # Should return empty list or actual devices without errors
        assert isinstance(devices, list)
        
        # Test recommendations (should work even with no devices)
        recommended = await detector.get_recommended_devices()
        assert isinstance(recommended, dict)
        
    @pytest.mark.asyncio
    async def test_device_validation_with_settings(self, test_settings):
        """Test device validation integrated with settings."""
        from src.utils.device_detection import validate_capture_setup
        
        # This will fail on systems without the exact test devices, but should handle gracefully
        video_device = test_settings.capture.video_device
        audio_device = test_settings.capture.audio_device
        
        is_valid, errors = await validate_capture_setup(video_device, audio_device)
        
        # Should return boolean and list, even if validation fails
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)
        
        if not is_valid:
            # Expected on test systems without real devices
            assert len(errors) > 0
            assert all(isinstance(error, str) for error in errors)


@pytest.mark.integration
class TestConfigurationIntegration:
    """Test configuration integration across all components."""
    
    def test_settings_integration_with_all_components(self, test_settings, temp_dir):
        """Test that settings properly configure all system components."""
        from src.storage.manager import StorageManager
        from src.audio.processor import AudioProcessor
        from src.vault.writer import VaultWriter
        from src.capture.webcam_capture import WebcamCapture
        
        # Create all components with test settings
        storage_manager = StorageManager(test_settings)
        audio_processor = AudioProcessor(test_settings)
        vault_writer = VaultWriter(test_settings)
        
        # Mock audio processor for webcam capture
        mock_audio_processor = Mock()
        webcam_capture = WebcamCapture(test_settings, mock_audio_processor)
        
        # Verify configuration propagation
        assert storage_manager.hot_storage_hours == test_settings.storage.hot_storage_hours
        assert audio_processor.settings.audio.sample_rate == test_settings.audio.sample_rate
        assert webcam_capture.settings.capture.video_device == test_settings.capture.video_device
        
        # Verify directory creation
        assert storage_manager.hot_storage.exists()
        assert storage_manager.warm_storage.exists()
        assert storage_manager.cold_storage.exists()
        assert webcam_capture.archive_dir.exists()
        
    def test_yaml_config_loading_integration(self, temp_dir):
        """Test YAML configuration loading with all components."""
        import yaml
        from src.main import Settings
        
        # Create test configuration
        config_data = {
            "capture": {
                "video_device": "Integration Test Camera",
                "audio_device": "Integration Test Microphone"
            },
            "audio": {
                "sample_rate": 44100,
                "whisper_model": "tiny"
            },
            "storage": {
                "archive_path": str(temp_dir / "integration_archive"),
                "hot_storage_hours": 12
            }
        }
        
        config_file = temp_dir / "integration_test.yaml"
        with open(config_file, 'w') as f:
            yaml.dump(config_data, f)
            
        # Load settings from file
        settings = Settings.load_from_file(config_file)
        
        # Verify configuration was loaded correctly
        assert settings.capture.video_device == "Integration Test Camera"
        assert settings.capture.audio_device == "Integration Test Microphone"
        assert settings.audio.sample_rate == 44100
        assert settings.audio.whisper_model == "tiny"
        assert settings.storage.archive_path == str(temp_dir / "integration_archive")
        assert settings.storage.hot_storage_hours == 12
        
        # Verify defaults are preserved
        assert settings.audio.vad_threshold == 0.5
        assert settings.activation.enabled is True


@pytest.mark.integration
class TestErrorHandlingAndRecovery:
    """Test error handling and recovery mechanisms."""
    
    @pytest.mark.asyncio
    async def test_webcam_capture_process_restart(self, test_settings):
        """Test webcam capture process restart on failure."""
        from src.capture.webcam_capture import WebcamCapture
        
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Mock failing process
        mock_process = Mock()
        mock_process.poll.return_value = 1  # Process died
        mock_process.terminate = Mock()
        mock_process.wait = Mock()
        
        capture.process = mock_process
        capture.is_recording = True
        capture._start_capture_process = AsyncMock()
        
        # Test restart mechanism
        await capture._restart_capture()
        
        # Verify restart sequence
        mock_process.terminate.assert_called_once()
        capture._start_capture_process.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_audio_processor_error_handling(self, test_settings, sample_audio_bytes):
        """Test audio processor error handling."""
        from src.audio.processor import AudioProcessor
        
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        
        # Mock VAD to raise exception
        processor.vad.detect_voice_activity = AsyncMock(side_effect=Exception("VAD error"))
        
        # Should handle error gracefully
        await processor.process_chunk(sample_audio_bytes, time.time())
        
        # Should still update basic stats despite error
        assert processor.stats["chunks_processed"] == 1
        
    @pytest.mark.asyncio
    async def test_storage_manager_error_recovery(self, test_settings):
        """Test storage manager error recovery."""
        from src.storage.manager import StorageManager
        
        storage_manager = StorageManager(test_settings)
        
        # Test with invalid data
        try:
            await storage_manager.store_video(None, {})
        except Exception:
            pass  # Expected to fail
            
        # Storage manager should still be functional
        metrics = storage_manager.get_storage_metrics()
        assert isinstance(metrics, dict)


@pytest.mark.performance
class TestPerformanceBaselines:
    """Test performance baselines for the capture system."""
    
    @pytest.mark.asyncio
    async def test_audio_processing_performance(self, test_settings, sample_audio_bytes):
        """Test audio processing performance meets requirements."""
        from src.audio.processor import AudioProcessor
        
        processor = AudioProcessor(test_settings)
        processor.is_running = True
        processor.vad.detect_voice_activity = AsyncMock(return_value=False)
        
        # Process multiple chunks and measure time
        start_time = time.time()
        
        for i in range(100):
            await processor.process_chunk(sample_audio_bytes, time.time() + i)
            
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should process 100 chunks in reasonable time (< 1 second for mocked processing)
        assert total_time < 1.0
        
        # Check average processing time
        avg_time = processor.stats["processing_time_total"] / processor.stats["chunks_processed"]
        assert avg_time < 0.01  # Less than 10ms per chunk
        
    @pytest.mark.asyncio 
    async def test_vault_writing_performance(self, vault_writer):
        """Test vault writing performance."""
        from datetime import datetime
        
        start_time = time.time()
        
        # Write multiple transcriptions
        for i in range(50):
            await vault_writer.write_transcription(
                text=f"Test transcription {i}",
                timestamp=datetime.now(),
                confidence=0.9,
                is_activation=False,
                activation_command=None
            )
            
        end_time = time.time()
        total_time = end_time - start_time
        
        # Should write 50 transcriptions quickly (< 2 seconds)
        assert total_time < 2.0
        
        # Verify all transcriptions were written
        assert vault_writer.stats["transcriptions_written"] >= 50