"""
Tests for the webcam capture module.
"""

import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import pytest
from pathlib import Path

from src.capture.webcam_capture import WebcamCapture


@pytest.mark.unit
class TestWebcamCaptureInitialization:
    """Test webcam capture initialization."""
    
    def test_webcam_capture_creation(self, test_settings):
        """Test creating a webcam capture instance."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        assert capture.settings == test_settings
        assert capture.audio_processor == audio_processor
        assert not capture.is_recording
        assert capture.process is None
        
        # Check archive directory is created
        expected_archive = Path(test_settings.storage.archive_path) / "video"
        assert capture.archive_dir == expected_archive
        assert capture.archive_dir.exists()
        
    def test_health_status_initial_state(self, test_settings):
        """Test initial health status."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        status = capture.get_health_status()
        
        assert status["is_recording"] is False
        assert status["uptime_seconds"] == 0
        assert status["process_running"] is False
        assert status["last_heartbeat_age_sec"] is None
        assert status["total_files_created"] == 0
        assert status["total_bytes_written"] == 0
        assert status["video_device"] == test_settings.capture.video_device
        assert status["audio_device"] == test_settings.capture.audio_device


@pytest.mark.unit
class TestWebcamCaptureLifecycle:
    """Test webcam capture lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_start_capture_already_running(self, test_settings):
        """Test starting capture when already running."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        
        # Should return early without starting process
        await capture.start()
        
        assert capture.process is None
        
    @pytest.mark.asyncio
    @patch('src.capture.webcam_capture.subprocess.Popen')
    async def test_start_capture_success(self, mock_popen, test_settings, mock_ffmpeg_process):
        """Test successful capture start."""
        mock_popen.return_value = mock_ffmpeg_process
        
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Mock the private methods
        capture._start_capture_process = AsyncMock()
        capture._monitor_capture = AsyncMock()
        
        await capture.start()
        
        assert capture.is_recording is True
        assert capture.start_time is not None
        capture._start_capture_process.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_stop_capture_not_running(self, test_settings):
        """Test stopping capture when not running."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Should return early
        await capture.stop()
        
        # No changes expected
        assert not capture.is_recording
        
    @pytest.mark.asyncio
    async def test_stop_capture_graceful(self, test_settings, mock_ffmpeg_process):
        """Test graceful capture stop."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        capture.process = mock_ffmpeg_process
        capture._wait_for_process = AsyncMock()
        
        await capture.stop()
        
        assert not capture.is_recording
        mock_ffmpeg_process.terminate.assert_called_once()
        capture._wait_for_process.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_stop_capture_force_kill(self, test_settings, mock_ffmpeg_process):
        """Test force killing process on timeout."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        capture.process = mock_ffmpeg_process
        
        # Mock timeout on graceful termination
        async def mock_wait_timeout():
            raise asyncio.TimeoutError()
            
        capture._wait_for_process = AsyncMock(side_effect=mock_wait_timeout)
        
        await capture.stop()
        
        assert not capture.is_recording
        mock_ffmpeg_process.terminate.assert_called_once()
        mock_ffmpeg_process.kill.assert_called_once()


@pytest.mark.unit
class TestFFmpegProcessManagement:
    """Test FFmpeg process management."""
    
    @patch('src.capture.webcam_capture.subprocess.Popen')
    async def test_start_capture_process_command_generation(self, mock_popen, test_settings, mock_ffmpeg_process):
        """Test FFmpeg command generation."""
        mock_popen.return_value = mock_ffmpeg_process
        
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        await capture._start_capture_process()
        
        # Check that Popen was called
        mock_popen.assert_called_once()
        
        # Verify the command structure
        call_args = mock_popen.call_args[0][0]  # First positional argument (the command)
        
        assert "ffmpeg" in call_args
        assert "-f" in call_args
        assert "dshow" in call_args
        assert "-i" in call_args
        
        # Check device specification
        device_spec = f"video={test_settings.capture.video_device}:audio={test_settings.capture.audio_device}"
        assert device_spec in call_args
        
        # Check encoding settings
        assert "-c:v" in call_args
        assert "libx264" in call_args
        assert "-c:a" in call_args
        assert "aac" in call_args
        
    @patch('src.capture.webcam_capture.subprocess.Popen')  
    async def test_start_capture_process_with_audio_task(self, mock_popen, test_settings, mock_ffmpeg_process):
        """Test that audio processing task is started."""
        mock_popen.return_value = mock_ffmpeg_process
        
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        with patch('asyncio.create_task') as mock_create_task:
            await capture._start_capture_process()
            
            # Should create task for audio processing
            mock_create_task.assert_called()
            
    @patch('src.capture.webcam_capture.subprocess.Popen')
    async def test_start_capture_process_failure(self, mock_popen, test_settings):
        """Test handling of FFmpeg process start failure."""
        mock_popen.side_effect = Exception("FFmpeg not found")
        
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        with pytest.raises(Exception, match="FFmpeg not found"):
            await capture._start_capture_process()


@pytest.mark.unit
class TestAudioStreamProcessing:
    """Test audio stream processing from FFmpeg."""
    
    @pytest.mark.asyncio
    async def test_process_audio_stream_no_process(self, test_settings):
        """Test audio processing when no process exists."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Should return early
        await capture._process_audio_stream()
        
        # No audio processing should occur
        audio_processor.process_chunk.assert_not_called()
        
    @pytest.mark.asyncio
    async def test_process_audio_stream_with_data(self, test_settings, sample_audio_bytes):
        """Test audio stream processing with real data."""
        audio_processor = Mock()
        audio_processor.process_chunk = AsyncMock()
        
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        
        # Mock process with audio data
        mock_process = Mock()
        mock_stdout = Mock()
        
        # Simulate audio data chunks
        audio_chunks = [
            sample_audio_bytes[:16000],  # First chunk
            sample_audio_bytes[16000:32000],  # Second chunk  
            b""  # End of stream
        ]
        
        mock_stdout.read.side_effect = audio_chunks
        mock_process.stdout = mock_stdout
        capture.process = mock_process
        
        await capture._process_audio_stream()
        
        # Should have processed audio chunks
        assert audio_processor.process_chunk.call_count >= 1
        assert capture.last_heartbeat is not None
        
    @pytest.mark.asyncio
    async def test_process_audio_stream_handles_errors(self, test_settings):
        """Test audio stream processing handles errors gracefully."""
        audio_processor = Mock()
        audio_processor.process_chunk = AsyncMock(side_effect=Exception("Processing error"))
        
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        
        # Mock process with audio data
        mock_process = Mock()
        mock_stdout = Mock()
        mock_stdout.read.side_effect = [b"test" * 8000, b""]  # Some data then end
        mock_process.stdout = mock_stdout
        capture.process = mock_process
        
        # Should not raise exception despite processing errors
        await capture._process_audio_stream()


@pytest.mark.unit
class TestCaptureMonitoring:
    """Test capture process monitoring and restart."""
    
    @pytest.mark.asyncio
    async def test_monitor_capture_process_died(self, test_settings, mock_ffmpeg_process):
        """Test monitoring detects dead process and restarts."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        capture.process = mock_ffmpeg_process
        capture._restart_capture = AsyncMock()
        
        # Simulate process death
        mock_ffmpeg_process.poll.return_value = 1  # Non-None means process died
        
        # Run one iteration of monitoring
        async def run_one_check():
            capture.is_recording = False  # Stop after one check
            await capture._monitor_capture()
            
        await run_one_check()
        
        capture._restart_capture.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_monitor_capture_heartbeat_timeout(self, test_settings, mock_ffmpeg_process):
        """Test monitoring detects heartbeat timeout and restarts."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        capture.is_recording = True
        capture.process = mock_ffmpeg_process
        capture._restart_capture = AsyncMock()
        
        # Set old heartbeat
        from datetime import datetime, timedelta
        capture.last_heartbeat = datetime.now() - timedelta(seconds=120)  # 2 minutes ago
        
        # Process is still running
        mock_ffmpeg_process.poll.return_value = None
        
        # Run one iteration of monitoring
        async def run_one_check():
            capture.is_recording = False  # Stop after one check
            await capture._monitor_capture()
            
        await run_one_check()
        
        capture._restart_capture.assert_called_once()
        
    @pytest.mark.asyncio
    async def test_restart_capture(self, test_settings, mock_ffmpeg_process):
        """Test capture restart process."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        capture.process = mock_ffmpeg_process
        capture._wait_for_process = AsyncMock()
        capture._start_capture_process = AsyncMock()
        
        await capture._restart_capture()
        
        # Should terminate, wait, and restart
        mock_ffmpeg_process.terminate.assert_called_once()
        capture._wait_for_process.assert_called_once()
        capture._start_capture_process.assert_called_once()


@pytest.mark.unit
class TestCaptureUtilities:
    """Test utility methods."""
    
    @pytest.mark.asyncio
    async def test_get_recent_files_empty(self, test_settings):
        """Test getting recent files when none exist."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        files = await capture.get_recent_files()
        
        assert files == []
        
    @pytest.mark.asyncio
    async def test_get_recent_files_with_files(self, test_settings, temp_dir):
        """Test getting recent files when some exist."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Create some test video files
        video_dir = capture.archive_dir
        video_dir.mkdir(parents=True, exist_ok=True)
        
        test_files = [
            video_dir / "video_20250109_120000.mp4",
            video_dir / "video_20250109_130000.mp4",
        ]
        
        for file_path in test_files:
            file_path.touch()  # Create empty file
            
        files = await capture.get_recent_files()
        
        # Should return the files, sorted by modification time (newest first)
        assert len(files) == 2
        assert all(f.name.startswith("video_") for f in files)
        
    @pytest.mark.asyncio
    async def test_trigger_high_quality_mode(self, test_settings):
        """Test triggering high quality mode."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Should not raise exceptions (implementation is TODO)
        await capture.trigger_high_quality_mode()
        
    @pytest.mark.asyncio  
    async def test_pause_capture(self, test_settings):
        """Test pausing capture."""
        audio_processor = Mock()
        capture = WebcamCapture(test_settings, audio_processor)
        
        # Should not raise exceptions (implementation is TODO)
        await capture.pause_capture(duration_seconds=60)