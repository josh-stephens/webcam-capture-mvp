#!/usr/bin/env python3
"""
Web-enabled main application

Runs the webcam capture system with the web interface for monitoring and control.
"""

import asyncio
import signal
import sys
from pathlib import Path

import structlog
import uvicorn
from main import Settings, WebcamCaptureApp

# Configure logging
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
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


class WebEnabledApp:
    """Web-enabled webcam capture application."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.webcam_app = WebcamCaptureApp(settings)
        self.shutdown_event = asyncio.Event()
        
    async def start(self):
        """Start both the webcam capture system and web interface."""
        try:
            logger.info("Starting web-enabled webcam capture system")
            
            # Start the webcam capture system in background
            webcam_task = asyncio.create_task(self.webcam_app.start())
            
            # Configure uvicorn
            config = uvicorn.Config(
                app=self.webcam_app.web_api.app,
                host="127.0.0.1",
                port=8090,
                log_level="info",
                loop="asyncio"
            )
            
            # Start web server
            server = uvicorn.Server(config)
            web_task = asyncio.create_task(server.serve())
            
            logger.info("Web interface available at http://127.0.0.1:8090")
            
            # Wait for shutdown signal
            await self.shutdown_event.wait()
            
            # Graceful shutdown
            logger.info("Shutting down...")
            
            # Stop webcam capture
            self.webcam_app.shutdown_event.set()
            await webcam_task
            
            # Stop web server
            server.should_exit = True
            await web_task
            
            logger.info("Shutdown complete")
            
        except Exception as e:
            logger.error("Application failed", error=str(e))
            raise
            
    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Received shutdown signal", signal=signum)
        self.shutdown_event.set()


async def main():
    """Main entry point."""
    try:
        # Load settings
        settings = Settings.load()
        
        # Create and start application
        app = WebEnabledApp(settings)
        
        # Setup signal handlers
        for sig in [signal.SIGINT, signal.SIGTERM]:
            signal.signal(sig, app.handle_shutdown)
        
        await app.start()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Application failed", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())