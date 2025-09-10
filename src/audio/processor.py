"""
Audio Processing Module

Handles real-time audio analysis including:
- Voice Activity Detection (VAD)  
- Speech recognition using Whisper
- Voice activation phrase detection
- Audio buffering and management
"""

import asyncio
import time
from collections import deque
from typing import Optional, Dict, Any, Callable
from datetime import datetime

import numpy as np
import structlog
from typing import Any

from audio.vad import VoiceActivityDetector
from vault.writer import VaultWriter


class AudioProcessor:
    """Real-time audio analysis and voice activation."""
    
    def __init__(self, settings: Any):
        self.settings = settings
        self.logger = structlog.get_logger()
        
        # Voice Activity Detection
        self.vad = VoiceActivityDetector(settings)
        
        # Vault integration
        self.vault_writer = VaultWriter(settings)
        
        # Audio buffering
        self.audio_buffer = deque(maxlen=settings.audio.buffer_duration_sec * settings.audio.sample_rate)
        self.voice_segments = []
        
        # Voice activation
        self.activation_phrases = {
            settings.activation.phrases["start_recording"]: self._handle_start_recording,
            settings.activation.phrases["mark_important"]: self._handle_mark_important,
            settings.activation.phrases["analyze_content"]: self._handle_analyze_content,
            settings.activation.phrases["show_status"]: self._handle_show_status,
            settings.activation.phrases["pause_recording"]: self._handle_pause_recording
        }
        
        # State management
        self.is_running = False
        self.last_activation_time = 0
        self.stats = {
            "chunks_processed": 0,
            "voice_segments_detected": 0,
            "activations_detected": 0,
            "processing_time_total": 0
        }
        
        # Whisper integration (lazy loaded)
        self._whisper_model = None
        
    async def start(self) -> None:
        """Start the audio processor."""
        if self.is_running:
            return
            
        try:
            self.logger.info("Starting audio processor")
            
            # Initialize VAD
            await self.vad.initialize()
            
            # Load Whisper model asynchronously
            await self._load_whisper_model()
            
            self.is_running = True
            self.logger.info("Audio processor started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start audio processor", error=str(e))
            raise
            
    async def stop(self) -> None:
        """Stop the audio processor."""
        if not self.is_running:
            return
            
        try:
            self.logger.info("Stopping audio processor")
            self.is_running = False
            
            # Cleanup resources
            await self.vad.cleanup()
            
            self.logger.info("Audio processor stopped")
            
        except Exception as e:
            self.logger.error("Error stopping audio processor", error=str(e))
            
    async def process_chunk(self, audio_data: bytes, timestamp: float) -> None:
        """Process incoming audio chunk."""
        if not self.is_running:
            return
            
        start_time = time.time()
        
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Add to circular buffer
            self.audio_buffer.extend(audio_array)
            
            # Voice activity detection
            has_voice = await self.vad.detect_voice_activity(audio_array)
            
            if has_voice:
                await self._handle_voice_detected(audio_array, timestamp)
            else:
                await self._handle_silence_detected(audio_array, timestamp)
                
            # Update statistics
            processing_time = time.time() - start_time
            self.stats["chunks_processed"] += 1
            self.stats["processing_time_total"] += processing_time
            
        except Exception as e:
            self.logger.error("Error processing audio chunk", error=str(e))
            
    async def _handle_voice_detected(self, audio_array: np.ndarray, timestamp: float) -> None:
        """Handle detected voice activity."""
        
        # Add to voice segments buffer
        self.voice_segments.append({
            "audio": audio_array,
            "timestamp": timestamp,
            "duration": len(audio_array) / self.settings.audio.sample_rate
        })
        
        # Keep only recent voice segments (last 10 seconds)
        cutoff_time = timestamp - 10.0
        self.voice_segments = [
            seg for seg in self.voice_segments 
            if seg["timestamp"] > cutoff_time
        ]
        
        self.stats["voice_segments_detected"] += 1
        
        # Check for voice activation phrases
        if len(self.voice_segments) >= 3:  # Need at least 3 seconds of voice
            await self._check_for_activation_phrases()
            
    async def _handle_silence_detected(self, audio_array: np.ndarray, timestamp: float) -> None:
        """Handle detected silence."""
        
        # Mark audio as potentially prunable after delay
        await self._mark_for_pruning(timestamp)
        
    async def _check_for_activation_phrases(self) -> None:
        """Check recent voice segments for activation phrases."""
        
        # Avoid rapid repeated checks
        current_time = time.time()
        if current_time - self.last_activation_time < self.settings.activation.cooldown_sec:
            return
            
        try:
            # Combine recent voice segments
            combined_audio = np.concatenate([seg["audio"] for seg in self.voice_segments[-5:]])
            
            # Transcribe using Whisper
            text = await self._transcribe_audio(combined_audio)
            
            if text:
                # Check for activation phrases
                text_lower = text.lower().strip()
                
                activation_detected = False
                matched_phrase = None
                
                for phrase, handler in self.activation_phrases.items():
                    if phrase in text_lower:
                        self.logger.info("Voice activation detected", 
                                       phrase=phrase, 
                                       full_text=text)
                        
                        # Execute handler
                        await handler()
                        
                        self.last_activation_time = current_time
                        self.stats["activations_detected"] += 1
                        activation_detected = True
                        matched_phrase = phrase
                        break
                        
                # Write transcription to vault
                await self.vault_writer.write_transcription(
                    text=text,
                    timestamp=datetime.now(),
                    confidence=0.9,  # TODO: Get actual confidence from Whisper
                    is_activation=activation_detected,
                    activation_command=matched_phrase
                )
                        
        except Exception as e:
            self.logger.error("Error checking activation phrases", error=str(e))
            
    async def _transcribe_audio(self, audio_array: np.ndarray) -> Optional[str]:
        """Transcribe audio using Whisper."""
        if not self._whisper_model:
            return None
            
        try:
            # Convert to float32 and normalize
            audio_float = audio_array.astype(np.float32) / 32768.0
            
            # Run transcription in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._whisper_model.transcribe, 
                audio_float
            )
            
            return result.get("text", "").strip()
            
        except Exception as e:
            self.logger.error("Error transcribing audio", error=str(e))
            return None
            
    async def _load_whisper_model(self) -> None:
        """Load Whisper model asynchronously."""
        try:
            import whisper
            
            self.logger.info("Loading Whisper model", model=self.settings.audio.whisper_model)
            
            # Load model in thread pool
            loop = asyncio.get_event_loop()
            self._whisper_model = await loop.run_in_executor(
                None, 
                whisper.load_model, 
                self.settings.audio.whisper_model
            )
            
            self.logger.info("Whisper model loaded successfully")
            
        except Exception as e:
            self.logger.error("Failed to load Whisper model", error=str(e))
            raise
            
    async def _mark_for_pruning(self, timestamp: float) -> None:
        """Mark audio segment for later pruning."""
        # TODO: Implement pruning logic
        # This would integrate with the storage manager
        pass
        
    # Voice activation handlers
    
    async def _handle_start_recording(self) -> None:
        """Handle 'computer start recording' activation."""
        self.logger.info("Activating high-quality recording mode")
        # TODO: Signal to webcam capture to switch modes
        
    async def _handle_mark_important(self) -> None:
        """Handle 'computer mark important' activation."""
        self.logger.info("Marking recent content as important")
        # TODO: Flag recent audio/video as permanent retention
        
    async def _handle_analyze_content(self) -> None:
        """Handle 'computer analyze this' activation."""
        self.logger.info("Starting content analysis")
        # TODO: Trigger deeper analysis of recent content
        
    async def _handle_show_status(self) -> None:
        """Handle 'computer show status' activation."""
        self.logger.info("Displaying system status")
        status = self.get_status()
        # TODO: Present status to user (voice response, UI, etc.)
        print("System Status:", status)
        
    async def _handle_pause_recording(self) -> None:
        """Handle 'computer pause recording' activation."""
        self.logger.info("Pausing recording temporarily")
        # TODO: Signal to webcam capture to pause
        
    def get_status(self) -> Dict[str, Any]:
        """Get current audio processor status and metrics."""
        
        avg_processing_time = 0
        if self.stats["chunks_processed"] > 0:
            avg_processing_time = (
                self.stats["processing_time_total"] / self.stats["chunks_processed"]
            )
            
        return {
            "is_running": self.is_running,
            "buffer_size": len(self.audio_buffer),
            "buffer_max_size": self.audio_buffer.maxlen,
            "voice_segments_count": len(self.voice_segments),
            "whisper_model_loaded": self._whisper_model is not None,
            "stats": {
                **self.stats,
                "avg_processing_time_ms": avg_processing_time * 1000
            },
            "vad_status": self.vad.get_status() if self.vad else None
        }
        
    async def get_recent_transcriptions(self, seconds: int = 60) -> list[Dict[str, Any]]:
        """Get transcriptions from recent voice segments."""
        # TODO: Implement transcription history
        return []
        
    def add_custom_activation_phrase(self, phrase: str, handler: Callable) -> None:
        """Add a custom activation phrase with handler."""
        self.activation_phrases[phrase.lower()] = handler
        self.logger.info("Added custom activation phrase", phrase=phrase)
        
    def remove_activation_phrase(self, phrase: str) -> None:
        """Remove an activation phrase."""
        if phrase.lower() in self.activation_phrases:
            del self.activation_phrases[phrase.lower()]
            self.logger.info("Removed activation phrase", phrase=phrase)