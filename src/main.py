#!/usr/bin/env python3
"""
Webcam Capture MVP - Main Entry Point

Personal Automation System - Foundational sensor module for continuous
audio/video capture with voice activation and intelligent content management.
"""

import asyncio
import logging
import signal
import sys
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

import structlog
import typer
from pydantic import BaseModel

from capture.webcam_capture import WebcamCapture
from audio.processor import AudioProcessor
from storage.manager import StorageManager
from web.api import WebAPI


class CaptureSettings(BaseModel):
    video_device: str = "USB Camera"
    audio_device: str = "Microphone"
    quality: str = "medium"
    frame_rate: int = 30
    resolution: str = "1280x720"

class StorageSettings(BaseModel):
    archive_path: str = "C:\\archive"
    max_daily_size_gb: int = 10
    retention_days: int = 30
    hot_storage_hours: int = 48
    warm_storage_days: int = 30
    cold_storage_years: int = 2
    enable_pruning: bool = True
    prune_silence_after_hours: int = 24
    prune_routine_after_days: int = 7
    keep_voice_segments: bool = True

class AudioSettings(BaseModel):
    vad_threshold: float = 0.5
    vad_model: str = "silero"
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    buffer_duration_sec: int = 30
    chunk_duration_sec: int = 1
    sample_rate: int = 16000
    channels: int = 1

class ActivationSettings(BaseModel):
    enabled: bool = True
    phrases: Dict[str, str] = {
        "start_recording": "computer start recording",
        "mark_important": "computer mark important", 
        "analyze_content": "computer analyze this",
        "show_status": "computer show status",
        "pause_recording": "computer pause recording"
    }
    confidence_threshold: float = 0.8
    response_timeout_sec: int = 2
    cooldown_sec: int = 1

class SystemSettings(BaseModel):
    log_level: str = "INFO"
    log_format: str = "json"
    log_file: str = "logs/webcam-capture.log"
    max_cpu_percent: int = 25
    max_memory_gb: int = 4
    health_check_interval_sec: int = 30
    restart_on_failure: bool = True
    max_restart_attempts: int = 3
    restart_delay_sec: int = 5

class Settings(BaseModel):
    """Application settings loaded from YAML config and environment variables."""
    capture: CaptureSettings = CaptureSettings()
    storage: StorageSettings = StorageSettings()
    audio: AudioSettings = AudioSettings()
    activation: ActivationSettings = ActivationSettings()
    system: SystemSettings = SystemSettings()
    
    @classmethod
    def load_from_file(cls, config_path: Path) -> "Settings":
        """Load settings from YAML configuration file."""
        try:
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)
            return cls(**config_data)
        except Exception as e:
            structlog.get_logger().warning(
                "Failed to load config file, using defaults", 
                path=str(config_path), 
                error=str(e)
            )
            return cls()
    
    @classmethod
    def load(cls) -> "Settings":
        """Load settings with defaults or from config file if available."""
        config_path = Path("config/default.yaml")
        if config_path.exists():
            return cls.load_from_file(config_path)
        else:
            return cls()


class WebcamCaptureApp:
    """Main application orchestrating webcam capture and processing."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = structlog.get_logger()
        self.shutdown_event = asyncio.Event()
        
        # Initialize components
        self.storage_manager = StorageManager(settings)
        self.audio_processor = AudioProcessor(settings)
        self.webcam_capture = WebcamCapture(settings, self.audio_processor)
        self.web_api = WebAPI(self)
        
    async def start(self) -> None:
        """Start the webcam capture system."""
        try:
            self.logger.info("Starting webcam capture system", 
                           video_device=self.settings.capture.video_device,
                           audio_device=self.settings.capture.audio_device)
            
            # Start storage manager
            await self.storage_manager.start()
            
            # Start audio processor
            await self.audio_processor.start()
            
            # Log system startup to vault
            await self.audio_processor.vault_writer.write_system_event(
                event_type="startup",
                description="Webcam capture system started successfully",
                metadata={
                    "video_device": self.settings.capture.video_device,
                    "audio_device": self.settings.capture.audio_device
                }
            )
            
            # Start webcam capture
            await self.webcam_capture.start()
            
            self.logger.info("Webcam capture system started successfully")
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
        except Exception as e:
            self.logger.error("Failed to start webcam capture system", error=str(e))
            raise
            
    async def stop(self) -> None:
        """Stop the webcam capture system gracefully."""
        try:
            self.logger.info("Stopping webcam capture system")
            
            # Log system shutdown to vault
            await self.audio_processor.vault_writer.write_system_event(
                event_type="shutdown",
                description="Webcam capture system stopping gracefully"
            )
            
            # Stop components in reverse order
            await self.webcam_capture.stop()
            await self.audio_processor.stop()
            await self.storage_manager.stop()
            
            self.logger.info("Webcam capture system stopped successfully")
            
        except Exception as e:
            self.logger.error("Error during system shutdown", error=str(e))
            
    def handle_shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signals gracefully."""
        self.logger.info("Received shutdown signal", signal=signum)
        self.shutdown_event.set()


def setup_logging(log_level: str) -> None:
    """Configure structured logging for the application."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper())
    )
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


app_typer = typer.Typer()


@app_typer.command()
def main(
    config_file: Optional[Path] = typer.Option(
        None, 
        "--config", 
        "-c", 
        help="Configuration file path"
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        "-l", 
        help="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
) -> None:
    """
    Start the webcam capture MVP system.
    
    This is the foundational sensor module for the Personal Automation System,
    providing continuous audio/video capture with voice activation and 
    intelligent content management.
    """
    
    # Load settings
    if config_file:
        settings = Settings.load_from_file(config_file)
    else:
        # Use default config file if it exists
        default_config = Path(__file__).parent.parent / "config" / "default.yaml"
        if default_config.exists():
            settings = Settings.load_from_file(default_config)
        else:
            settings = Settings()
    
    # Override log level if provided
    if log_level:
        settings.system.log_level = log_level
        
    # Setup logging
    setup_logging(settings.system.log_level)
    logger = structlog.get_logger()
    
    logger.info("Initializing webcam capture MVP",
               version="1.0.0",
               config_file=str(config_file) if config_file else None)
    
    # Create application
    app = WebcamCaptureApp(settings)
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, app.handle_shutdown)
    signal.signal(signal.SIGTERM, app.handle_shutdown)
    
    try:
        # Run the application
        asyncio.run(app.start())
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        
    except Exception as e:
        logger.error("Application failed", error=str(e))
        sys.exit(1)
        
    finally:
        # Ensure clean shutdown
        asyncio.run(app.stop())
        logger.info("Application shutdown complete")


if __name__ == "__main__":
    app_typer()