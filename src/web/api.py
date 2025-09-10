"""
Web API Module

Provides REST API and WebSocket endpoints for monitoring and controlling
the webcam capture system in real-time.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
from pydantic import BaseModel

logger = structlog.get_logger()


class SystemStatus(BaseModel):
    """System status response model."""
    is_running: bool
    video_capture_active: bool
    audio_processing_active: bool
    vad_active: bool
    whisper_loaded: bool
    storage_usage: Dict[str, Any]
    uptime_seconds: float
    last_voice_activation: Optional[str]
    recent_transcriptions: List[Dict[str, Any]]


class SensorControl(BaseModel):
    """Sensor control request model."""
    sensor_type: str  # "video", "audio", "vad", "whisper"
    enabled: bool


class VaultEntry(BaseModel):
    """Vault entry model for display."""
    timestamp: str
    type: str  # "transcription", "activation", "system_event"
    content: str
    confidence: Optional[float] = None


class ConnectionManager:
    """Manages WebSocket connections for real-time updates."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("WebSocket client connected", total_connections=len(self.active_connections))
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("WebSocket client disconnected", total_connections=len(self.active_connections))
        
    async def broadcast_status(self, status: Dict[str, Any]):
        """Broadcast system status to all connected clients."""
        if not self.active_connections:
            return
            
        message = json.dumps({
            "type": "status_update",
            "data": status,
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning("Failed to send WebSocket message", error=str(e))
                disconnected.append(connection)
                
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
            
    async def broadcast_vault_entry(self, entry: VaultEntry):
        """Broadcast new vault entry to all connected clients."""
        if not self.active_connections:
            return
            
        message = json.dumps({
            "type": "vault_entry",
            "data": entry.dict(),
            "timestamp": datetime.now().isoformat()
        })
        
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.warning("Failed to send WebSocket message", error=str(e))
                disconnected.append(connection)
                
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


class WebAPI:
    """FastAPI web application for system monitoring and control."""
    
    def __init__(self, webcam_app):
        self.webcam_app = webcam_app
        self.app = FastAPI(
            title="Webcam Capture MVP",
            description="Personal Automation System - Webcam Capture Control Panel",
            version="1.0.0"
        )
        self.connection_manager = ConnectionManager()
        self.start_time = datetime.now()
        
        # Setup static files and templates
        static_path = Path(__file__).parent / "static"
        static_path.mkdir(exist_ok=True)
        
        templates_path = Path(__file__).parent / "templates"
        templates_path.mkdir(exist_ok=True)
        
        self.app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
        self.templates = Jinja2Templates(directory=str(templates_path))
        
        self._setup_routes()
        
        # Start status broadcast task
        self._status_task = None
        
    def _setup_routes(self):
        """Setup API routes."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            """Serve the main dashboard."""
            return self.templates.TemplateResponse("dashboard.html", {
                "request": request,
                "title": "Webcam Capture Control Panel"
            })
            
        @self.app.get("/api/status", response_model=SystemStatus)
        async def get_status():
            """Get current system status."""
            try:
                # Get status from components
                storage_status = self.webcam_app.storage_manager.get_status()
                audio_status = self.webcam_app.audio_processor.get_status()
                capture_status = self.webcam_app.webcam_capture.get_status()
                
                # Get recent transcriptions
                recent_transcriptions = []
                try:
                    recent_transcriptions = await self.webcam_app.audio_processor.get_recent_transcriptions(60)
                except Exception as e:
                    logger.warning("Failed to get recent transcriptions", error=str(e))
                
                uptime = (datetime.now() - self.start_time).total_seconds()
                
                return SystemStatus(
                    is_running=True,
                    video_capture_active=capture_status.get("is_recording", False),
                    audio_processing_active=audio_status.get("is_running", False),
                    vad_active=audio_status.get("vad_status", {}).get("is_loaded", False),
                    whisper_loaded=audio_status.get("whisper_model_loaded", False),
                    storage_usage=storage_status,
                    uptime_seconds=uptime,
                    last_voice_activation=None,  # TODO: Track this
                    recent_transcriptions=recent_transcriptions
                )
                
            except Exception as e:
                logger.error("Failed to get system status", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.post("/api/control")
        async def control_sensor(control: SensorControl):
            """Control individual sensors."""
            try:
                if control.sensor_type == "video":
                    if control.enabled:
                        await self.webcam_app.webcam_capture.resume_video()
                    else:
                        await self.webcam_app.webcam_capture.pause_video()
                        
                elif control.sensor_type == "audio":
                    if control.enabled:
                        await self.webcam_app.audio_processor.start()
                    else:
                        await self.webcam_app.audio_processor.stop()
                        
                elif control.sensor_type == "vad":
                    # Toggle VAD specifically
                    vad = self.webcam_app.audio_processor.vad
                    if control.enabled:
                        await vad.initialize()
                    else:
                        await vad.cleanup()
                        
                else:
                    raise HTTPException(status_code=400, detail=f"Unknown sensor type: {control.sensor_type}")
                    
                return {"status": "success", "message": f"{control.sensor_type} {'enabled' if control.enabled else 'disabled'}"}
                
            except Exception as e:
                logger.error("Failed to control sensor", sensor=control.sensor_type, error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.get("/api/vault/recent")
        async def get_recent_vault_entries(limit: int = 50):
            """Get recent vault entries."""
            try:
                vault_writer = self.webcam_app.audio_processor.vault_writer
                
                # Get today's daily note path
                today = datetime.now().date()
                daily_note_path = vault_writer.daily_notes_path / f"{today.strftime('%Y-%m-%d')}.md"
                
                entries = []
                if daily_note_path.exists():
                    with open(daily_note_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                    # Parse entries (simplified parsing)
                    lines = content.split('\n')
                    for line in lines:
                        if line.startswith('[VOICE]') or line.startswith('[CMD]') or line.startswith('['):
                            # Extract timestamp and content
                            if '**' in line:
                                try:
                                    # Parse: [TYPE] **HH:MM:SS** - content
                                    parts = line.split('**')
                                    if len(parts) >= 3:
                                        entry_type = line.split(']')[0] + ']'
                                        timestamp = parts[1]
                                        content = parts[2].replace(' - ', '', 1)
                                        
                                        entries.append(VaultEntry(
                                            timestamp=timestamp,
                                            type=entry_type,
                                            content=content.strip()
                                        ))
                                except Exception as e:
                                    logger.warning("Failed to parse vault entry", line=line, error=str(e))
                                    
                return entries[-limit:] if entries else []
                
            except Exception as e:
                logger.error("Failed to get vault entries", error=str(e))
                raise HTTPException(status_code=500, detail=str(e))
                
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await self.connection_manager.connect(websocket)
            try:
                while True:
                    # Send periodic status updates
                    await asyncio.sleep(2)
                    status = await get_status()
                    await self.connection_manager.broadcast_status(status.dict())
                    
            except WebSocketDisconnect:
                self.connection_manager.disconnect(websocket)
                
    async def start_status_broadcasting(self):
        """Start broadcasting status updates."""
        self._status_task = asyncio.create_task(self._status_broadcast_loop())
        
    async def stop_status_broadcasting(self):
        """Stop broadcasting status updates."""
        if self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
                
    async def _status_broadcast_loop(self):
        """Background task to broadcast status updates."""
        while True:
            try:
                await asyncio.sleep(5)  # Broadcast every 5 seconds
                if self.connection_manager.active_connections:
                    # Get current status and broadcast
                    # This will be called by WebSocket connections
                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in status broadcast loop", error=str(e))
                await asyncio.sleep(10)  # Wait before retrying