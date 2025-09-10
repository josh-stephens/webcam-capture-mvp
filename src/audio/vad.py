"""
Voice Activity Detection Module

Handles voice activity detection using Silero VAD or WebRTC VAD
for real-time audio stream processing.
"""

import asyncio
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

import numpy as np
import structlog
from typing import Any


class VADInterface(ABC):
    """Abstract interface for Voice Activity Detection."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the VAD model."""
        pass
        
    @abstractmethod
    async def detect_voice_activity(self, audio: np.ndarray) -> bool:
        """Detect voice activity in audio chunk."""
        pass
        
    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources."""
        pass
        
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get VAD status and metrics."""
        pass


class SileroVAD(VADInterface):
    """Silero Voice Activity Detection implementation."""
    
    def __init__(self, settings: Any):
        self.settings = settings
        self.logger = structlog.get_logger()
        
        self.model = None
        self.sample_rate = settings.audio.sample_rate
        self.threshold = settings.audio.vad_threshold
        
        # Statistics
        self.stats = {
            "detections_total": 0,
            "voice_detected": 0,
            "silence_detected": 0,
            "processing_time_total": 0
        }
        
    async def initialize(self) -> None:
        """Initialize Silero VAD model."""
        try:
            self.logger.info("Loading Silero VAD model")
            
            # Dynamic import to handle optional dependency
            import torch
            
            # Load model in thread pool
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None,
                self._load_silero_model
            )
            
            self.logger.info("Silero VAD model loaded successfully")
            
        except ImportError:
            self.logger.error("Silero VAD dependencies not installed")
            raise
        except Exception as e:
            self.logger.error("Failed to load Silero VAD model", error=str(e))
            raise
            
    def _load_silero_model(self):
        """Load Silero model (runs in thread pool)."""
        import torch
        
        model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            onnx=False
        )
        
        return model
        
    async def detect_voice_activity(self, audio: np.ndarray) -> bool:
        """Detect voice activity using Silero VAD."""
        if not self.model:
            return False
            
        try:
            import time
            start_time = time.time()
            
            # Convert to tensor and normalize
            import torch
            audio_tensor = torch.from_numpy(audio.astype(np.float32))
            
            # Ensure audio is the right length (minimum 512 samples)
            if len(audio_tensor) < 512:
                # Pad with zeros
                padding_needed = 512 - len(audio_tensor)
                audio_tensor = torch.nn.functional.pad(audio_tensor, (0, padding_needed))
            
            # Run detection in thread pool
            loop = asyncio.get_event_loop()
            confidence = await loop.run_in_executor(
                None,
                self._run_vad_detection,
                audio_tensor
            )
            
            # Apply threshold
            has_voice = confidence > self.threshold
            
            # Update statistics
            processing_time = time.time() - start_time
            self.stats["detections_total"] += 1
            self.stats["processing_time_total"] += processing_time
            
            if has_voice:
                self.stats["voice_detected"] += 1
            else:
                self.stats["silence_detected"] += 1
                
            return has_voice
            
        except Exception as e:
            self.logger.error("Error in Silero VAD detection", error=str(e))
            return False
            
    def _run_vad_detection(self, audio_tensor):
        """Run VAD detection (runs in thread pool)."""
        return self.model(audio_tensor, self.sample_rate).item()
        
    async def cleanup(self) -> None:
        """Clean up Silero VAD resources."""
        self.model = None
        self.logger.info("Silero VAD cleanup completed")
        
    def get_status(self) -> Dict[str, Any]:
        """Get Silero VAD status and metrics."""
        
        avg_processing_time = 0
        voice_ratio = 0
        
        if self.stats["detections_total"] > 0:
            avg_processing_time = (
                self.stats["processing_time_total"] / self.stats["detections_total"]
            )
            voice_ratio = self.stats["voice_detected"] / self.stats["detections_total"]
            
        return {
            "model_type": "silero",
            "model_loaded": self.model is not None,
            "threshold": self.threshold,
            "sample_rate": self.sample_rate,
            "stats": {
                **self.stats,
                "avg_processing_time_ms": avg_processing_time * 1000,
                "voice_ratio": voice_ratio
            }
        }


class WebRTCVAD(VADInterface):
    """WebRTC Voice Activity Detection implementation."""
    
    def __init__(self, settings: Any):
        self.settings = settings
        self.logger = structlog.get_logger()
        
        self.vad = None
        self.sample_rate = settings.audio.sample_rate
        self.aggressiveness = int(settings.audio.vad_threshold * 3)  # 0-3 scale
        
        # WebRTC VAD requires specific frame sizes
        self.frame_duration_ms = 30  # 10, 20, or 30 ms
        self.frame_size = int(self.sample_rate * self.frame_duration_ms / 1000)
        
        # Statistics
        self.stats = {
            "detections_total": 0,
            "voice_detected": 0,
            "silence_detected": 0,
            "processing_time_total": 0
        }
        
    async def initialize(self) -> None:
        """Initialize WebRTC VAD."""
        try:
            self.logger.info("Initializing WebRTC VAD")
            
            import webrtcvad
            
            self.vad = webrtcvad.Vad(self.aggressiveness)
            
            self.logger.info("WebRTC VAD initialized successfully",
                           aggressiveness=self.aggressiveness,
                           frame_duration_ms=self.frame_duration_ms)
            
        except ImportError:
            self.logger.error("WebRTC VAD dependencies not installed")
            raise
        except Exception as e:
            self.logger.error("Failed to initialize WebRTC VAD", error=str(e))
            raise
            
    async def detect_voice_activity(self, audio: np.ndarray) -> bool:
        """Detect voice activity using WebRTC VAD."""
        if not self.vad:
            return False
            
        try:
            import time
            start_time = time.time()
            
            # WebRTC VAD requires 16-bit PCM at specific sample rates
            if self.sample_rate not in [8000, 16000, 32000, 48000]:
                self.logger.warning("WebRTC VAD: Unsupported sample rate", 
                                  sample_rate=self.sample_rate)
                return False
                
            # Process audio in fixed-size frames
            voice_frames = 0
            total_frames = 0
            
            # Convert to bytes
            audio_bytes = audio.astype(np.int16).tobytes()
            
            # Process in frame-sized chunks
            for i in range(0, len(audio_bytes), self.frame_size * 2):  # 2 bytes per sample
                frame_bytes = audio_bytes[i:i + self.frame_size * 2]
                
                # Ensure frame is correct size
                if len(frame_bytes) == self.frame_size * 2:
                    try:
                        is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
                        if is_speech:
                            voice_frames += 1
                        total_frames += 1
                    except Exception as e:
                        self.logger.debug("WebRTC VAD frame processing error", error=str(e))
                        continue
                        
            # Determine overall voice activity
            has_voice = False
            if total_frames > 0:
                voice_ratio = voice_frames / total_frames
                has_voice = voice_ratio > 0.3  # At least 30% of frames have voice
                
            # Update statistics
            processing_time = time.time() - start_time
            self.stats["detections_total"] += 1
            self.stats["processing_time_total"] += processing_time
            
            if has_voice:
                self.stats["voice_detected"] += 1
            else:
                self.stats["silence_detected"] += 1
                
            return has_voice
            
        except Exception as e:
            self.logger.error("Error in WebRTC VAD detection", error=str(e))
            return False
            
    async def cleanup(self) -> None:
        """Clean up WebRTC VAD resources."""
        self.vad = None
        self.logger.info("WebRTC VAD cleanup completed")
        
    def get_status(self) -> Dict[str, Any]:
        """Get WebRTC VAD status and metrics."""
        
        avg_processing_time = 0
        voice_ratio = 0
        
        if self.stats["detections_total"] > 0:
            avg_processing_time = (
                self.stats["processing_time_total"] / self.stats["detections_total"]
            )
            voice_ratio = self.stats["voice_detected"] / self.stats["detections_total"]
            
        return {
            "model_type": "webrtc",
            "model_loaded": self.vad is not None,
            "aggressiveness": self.aggressiveness,
            "sample_rate": self.sample_rate,
            "frame_duration_ms": self.frame_duration_ms,
            "stats": {
                **self.stats,
                "avg_processing_time_ms": avg_processing_time * 1000,
                "voice_ratio": voice_ratio
            }
        }


class VoiceActivityDetector:
    """Factory and facade for Voice Activity Detection."""
    
    def __init__(self, settings: Any):
        self.settings = settings
        self.logger = structlog.get_logger()
        
        # Create VAD implementation based on settings
        vad_model = settings.audio.vad_model.lower()
        
        if vad_model == 'silero':
            self.vad = SileroVAD(settings)
        elif vad_model == 'webrtc':
            self.vad = WebRTCVAD(settings)
        else:
            raise ValueError(f"Unsupported VAD model: {vad_model}")
            
    async def initialize(self) -> None:
        """Initialize the VAD implementation."""
        await self.vad.initialize()
        
    async def detect_voice_activity(self, audio: np.ndarray) -> bool:
        """Detect voice activity in audio chunk."""
        return await self.vad.detect_voice_activity(audio)
        
    async def cleanup(self) -> None:
        """Clean up VAD resources."""
        await self.vad.cleanup()
        
    def get_status(self) -> Dict[str, Any]:
        """Get VAD status and metrics."""
        return self.vad.get_status()