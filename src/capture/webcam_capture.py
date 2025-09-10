"""
Webcam Capture Module

Handles continuous webcam capture using FFmpeg with dual output streams:
- Full video recording to archive files
- Real-time audio stream for processing
"""

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any, AsyncGenerator
from datetime import datetime

import structlog
from typing import Any


class WebcamCapture:
    """Continuous webcam capture with dual output streams."""
    
    def __init__(self, settings: Any, audio_processor):
        self.settings = settings
        self.audio_processor = audio_processor
        self.logger = structlog.get_logger()
        
        # State management
        self.is_recording = False
        self.process: Optional[subprocess.Popen] = None
        self.archive_dir = Path(settings.storage.archive_path) / "video"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Health monitoring
        self.start_time: Optional[datetime] = None
        self.last_heartbeat: Optional[datetime] = None
        self.total_files_created = 0
        self.total_bytes_written = 0
        
    async def start(self) -> None:
        """Start continuous webcam capture."""
        if self.is_recording:
            self.logger.warning("Capture already running")
            return
            
        try:
            self.logger.info("Starting webcam capture",
                           video_device=self.settings.capture.video_device,
                           audio_device=self.settings.capture.audio_device,
                           archive_path=str(self.archive_dir))
            
            # Start the capture process
            await self._start_capture_process()
            
            # Start monitoring task
            asyncio.create_task(self._monitor_capture())
            
            self.is_recording = True
            self.start_time = datetime.now()
            
            self.logger.info("Webcam capture started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start webcam capture", error=str(e))
            raise
            
    async def stop(self) -> None:
        """Stop webcam capture gracefully."""
        if not self.is_recording:
            return
            
        try:
            self.logger.info("Stopping webcam capture")
            
            self.is_recording = False
            
            if self.process:
                # Send graceful termination signal
                self.process.terminate()
                
                # Wait for process to exit
                try:
                    await asyncio.wait_for(
                        self._wait_for_process(), 
                        timeout=10.0
                    )
                except asyncio.TimeoutError:
                    self.logger.warning("Process didn't terminate gracefully, forcing kill")
                    self.process.kill()
                    
            self.logger.info("Webcam capture stopped")
            
        except Exception as e:
            self.logger.error("Error stopping webcam capture", error=str(e))
            
    async def _start_capture_process(self) -> None:
        """Start the FFmpeg capture process with dual output."""
        
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_file = self.archive_dir / f"video_{timestamp}.mp4"
        
        # Build FFmpeg command for dual output
        cmd = [
            "ffmpeg",
            "-f", "dshow",  # DirectShow for Windows
            "-i", f"video={self.settings.capture.video_device}:audio={self.settings.capture.audio_device}",
            
            # Video encoding settings
            "-c:v", "libx264",
            "-preset", "ultrafast",  # Low latency
            "-crf", "23",           # Quality setting
            
            # Audio encoding settings  
            "-c:a", "aac",
            "-ar", "16000",         # 16kHz for speech processing
            "-ac", "1",             # Mono audio
            
            # Dual output using tee muxer
            "-f", "tee",
            f"[movflags=+faststart]{video_file}|[f=wav]pipe:1"
        ]
        
        self.logger.info("Starting FFmpeg process",
                        command=" ".join(cmd),
                        output_file=str(video_file))
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0  # Unbuffered for real-time processing
            )
            
            # Start audio processing task
            asyncio.create_task(self._process_audio_stream())
            
        except Exception as e:
            self.logger.error("Failed to start FFmpeg process", error=str(e))
            raise
            
    async def _process_audio_stream(self) -> None:
        """Process the real-time audio stream from FFmpeg."""
        if not self.process or not self.process.stdout:
            return
            
        self.logger.info("Starting audio stream processing")
        
        try:
            # Read audio data in chunks
            chunk_size = 1024
            buffer = b""
            
            while self.is_recording and self.process:
                try:
                    # Read chunk from FFmpeg stdout
                    chunk = self.process.stdout.read(chunk_size)
                    
                    if not chunk:
                        # End of stream or process stopped
                        break
                        
                    buffer += chunk
                    
                    # Process when we have enough data (1 second at 16kHz)
                    if len(buffer) >= 32000:  # 16000 samples * 2 bytes
                        audio_data = buffer[:32000]
                        buffer = buffer[32000:]
                        
                        # Send to audio processor
                        await self.audio_processor.process_chunk(
                            audio_data, 
                            time.time()
                        )
                        
                        self.last_heartbeat = datetime.now()
                        
                except Exception as e:
                    self.logger.error("Error processing audio chunk", error=str(e))
                    continue
                    
        except Exception as e:
            self.logger.error("Audio stream processing failed", error=str(e))
        finally:
            self.logger.info("Audio stream processing stopped")
            
    async def _monitor_capture(self) -> None:
        """Monitor capture process health and restart if needed."""
        
        while self.is_recording:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self.process:
                    continue
                    
                # Check if process is still running
                if self.process.poll() is not None:
                    self.logger.warning("Capture process died, restarting",
                                      return_code=self.process.returncode)
                    await self._restart_capture()
                    continue
                    
                # Check heartbeat
                if self.last_heartbeat:
                    heartbeat_age = (datetime.now() - self.last_heartbeat).total_seconds()
                    if heartbeat_age > 60:  # No audio data for 1 minute
                        self.logger.warning("No audio data received, restarting capture",
                                          heartbeat_age_sec=heartbeat_age)
                        await self._restart_capture()
                        
            except Exception as e:
                self.logger.error("Error in capture monitoring", error=str(e))
                
    async def _restart_capture(self) -> None:
        """Restart the capture process."""
        try:
            self.logger.info("Restarting capture process")
            
            # Stop current process
            if self.process:
                self.process.terminate()
                await self._wait_for_process()
                
            # Wait a moment before restarting
            await asyncio.sleep(2)
            
            # Start new process
            await self._start_capture_process()
            
            self.logger.info("Capture process restarted successfully")
            
        except Exception as e:
            self.logger.error("Failed to restart capture process", error=str(e))
            
    async def _wait_for_process(self) -> None:
        """Wait for the FFmpeg process to exit."""
        if not self.process:
            return
            
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.process.wait)
        
    def get_health_status(self) -> Dict[str, Any]:
        """Return current health and performance metrics."""
        uptime_seconds = 0
        if self.start_time:
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            
        heartbeat_age = None
        if self.last_heartbeat:
            heartbeat_age = (datetime.now() - self.last_heartbeat).total_seconds()
            
        return {
            "is_recording": self.is_recording,
            "uptime_seconds": uptime_seconds,
            "process_running": self.process is not None and self.process.poll() is None,
            "last_heartbeat_age_sec": heartbeat_age,
            "total_files_created": self.total_files_created,
            "total_bytes_written": self.total_bytes_written,
            "archive_directory": str(self.archive_dir),
            "video_device": self.settings.capture.video_device,
            "audio_device": self.settings.capture.audio_device
        }
        
    async def pause_video(self) -> None:
        """Pause video recording while keeping audio processing active."""
        if not self.is_recording:
            return
            
        try:
            self.logger.info("Pausing video recording")
            
            # Stop the FFmpeg process but keep is_recording for audio
            if self.process:
                self.process.terminate()
                await self._wait_for_process()
                self.process = None
                
            self.logger.info("Video recording paused")
            
        except Exception as e:
            self.logger.error("Failed to pause video recording", error=str(e))
            
    async def resume_video(self) -> None:
        """Resume video recording."""
        if self.process is not None:
            return  # Already recording
            
        try:
            self.logger.info("Resuming video recording")
            await self._start_capture_process()
            self.logger.info("Video recording resumed")
            
        except Exception as e:
            self.logger.error("Failed to resume video recording", error=str(e))
            
    def get_status(self) -> Dict[str, Any]:
        """Get current status for web API."""
        return self.get_health_status()
        
    async def get_recent_files(self, hours: int = 24) -> list[Path]:
        """Get list of video files created in the last N hours."""
        cutoff_time = time.time() - (hours * 3600)
        recent_files = []
        
        for file_path in self.archive_dir.glob("video_*.mp4"):
            if file_path.stat().st_mtime > cutoff_time:
                recent_files.append(file_path)
                
        return sorted(recent_files, key=lambda f: f.stat().st_mtime, reverse=True)
        
    async def trigger_high_quality_mode(self) -> None:
        """Switch to high-quality capture mode."""
        self.logger.info("Switching to high-quality capture mode")
        # TODO: Implement quality mode switching
        # This might involve restarting with different FFmpeg parameters
        
    async def pause_capture(self, duration_seconds: Optional[int] = None) -> None:
        """Temporarily pause capture."""
        self.logger.info("Pausing capture", duration_seconds=duration_seconds)
        # TODO: Implement pause functionality
        # This might involve stopping the process and restarting after duration