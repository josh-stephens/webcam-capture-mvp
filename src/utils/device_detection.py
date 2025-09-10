"""
USB Device Detection Module

Provides utilities for detecting and validating USB webcams and audio devices
on Windows systems. Helps ensure hardware compatibility before attempting capture.
"""

import subprocess
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import asyncio

import structlog


class DeviceType(Enum):
    """Types of devices we can detect."""
    VIDEO = "video"
    AUDIO = "audio"
    BOTH = "both"


class DeviceStatus(Enum):
    """Device availability status."""
    AVAILABLE = "available"
    IN_USE = "in_use"
    ERROR = "error"
    NOT_FOUND = "not_found"


@dataclass
class DeviceInfo:
    """Information about a detected device."""
    name: str
    device_type: DeviceType
    driver: str
    status: DeviceStatus
    video_formats: List[str] = None
    audio_formats: List[str] = None
    max_resolution: str = None
    max_fps: int = None
    device_index: int = None
    friendly_name: str = None
    hardware_id: str = None


class DeviceDetector:
    """Detects and validates USB audio/video devices on Windows."""
    
    def __init__(self):
        self.logger = structlog.get_logger()
        self._cached_devices = {}
        self._cache_timestamp = 0
        self._cache_ttl = 30  # Cache for 30 seconds
        
    async def discover_devices(self, device_type: DeviceType = DeviceType.BOTH) -> List[DeviceInfo]:
        """
        Discover available audio/video devices.
        
        Args:
            device_type: Type of devices to discover
            
        Returns:
            List of discovered devices
        """
        try:
            self.logger.info("Starting device discovery", device_type=device_type.value)
            
            devices = []
            
            if device_type in (DeviceType.VIDEO, DeviceType.BOTH):
                video_devices = await self._discover_video_devices()
                devices.extend(video_devices)
                
            if device_type in (DeviceType.AUDIO, DeviceType.BOTH):
                audio_devices = await self._discover_audio_devices()
                devices.extend(audio_devices)
                
            self.logger.info("Device discovery completed", 
                           device_count=len(devices),
                           device_type=device_type.value)
            
            return devices
            
        except Exception as e:
            self.logger.error("Device discovery failed", error=str(e))
            return []
    
    async def _discover_video_devices(self) -> List[DeviceInfo]:
        """Discover video devices using FFmpeg's dshow."""
        devices = []
        
        try:
            # Use FFmpeg to list DirectShow video devices
            cmd = ["ffmpeg", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
            
            self.logger.debug("Running FFmpeg device discovery", command=" ".join(cmd))
            
            result = await self._run_command(cmd)
            
            # Parse FFmpeg output to extract video devices
            devices = self._parse_ffmpeg_video_devices(result.stderr)
            
            # Get additional device details for each discovered device
            for device in devices:
                await self._enrich_video_device_info(device)
                
        except Exception as e:
            self.logger.error("Video device discovery failed", error=str(e))
            
        return devices
    
    async def _discover_audio_devices(self) -> List[DeviceInfo]:
        """Discover audio input devices using FFmpeg's dshow."""
        devices = []
        
        try:
            # Use FFmpeg to list DirectShow audio devices  
            cmd = ["ffmpeg", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
            
            result = await self._run_command(cmd)
            
            # Parse FFmpeg output to extract audio devices
            devices = self._parse_ffmpeg_audio_devices(result.stderr)
            
            # Get additional device details
            for device in devices:
                await self._enrich_audio_device_info(device)
                
        except Exception as e:
            self.logger.error("Audio device discovery failed", error=str(e))
            
        return devices
    
    def _parse_ffmpeg_video_devices(self, ffmpeg_output: str) -> List[DeviceInfo]:
        """Parse FFmpeg output to extract video device information."""
        devices = []
        
        # Pattern to match DirectShow video devices
        # Example: [dshow @ 000001] "USB Camera" (video)
        video_pattern = r'\[dshow[^\]]*\]\s+"([^"]+)"\s+\(video\)'
        
        matches = re.findall(video_pattern, ffmpeg_output)
        
        for i, device_name in enumerate(matches):
            device = DeviceInfo(
                name=device_name,
                device_type=DeviceType.VIDEO,
                driver="dshow",
                status=DeviceStatus.AVAILABLE,
                device_index=i,
                friendly_name=device_name
            )
            devices.append(device)
            
        self.logger.debug("Parsed video devices", count=len(devices))
        return devices
    
    def _parse_ffmpeg_audio_devices(self, ffmpeg_output: str) -> List[DeviceInfo]:
        """Parse FFmpeg output to extract audio device information."""
        devices = []
        
        # Pattern to match DirectShow audio devices
        # Example: [dshow @ 000001] "Microphone (USB Audio Device)" (audio)
        audio_pattern = r'\[dshow[^\]]*\]\s+"([^"]+)"\s+\(audio\)'
        
        matches = re.findall(audio_pattern, ffmpeg_output)
        
        for i, device_name in enumerate(matches):
            device = DeviceInfo(
                name=device_name,
                device_type=DeviceType.AUDIO,
                driver="dshow",
                status=DeviceStatus.AVAILABLE,
                device_index=i,
                friendly_name=device_name
            )
            devices.append(device)
            
        self.logger.debug("Parsed audio devices", count=len(devices))
        return devices
    
    async def _enrich_video_device_info(self, device: DeviceInfo) -> None:
        """Get additional information about a video device."""
        try:
            # Query device capabilities using FFmpeg
            cmd = [
                "ffmpeg", "-f", "dshow", 
                "-list_options", "true",
                "-i", f"video={device.name}"
            ]
            
            result = await self._run_command(cmd)
            
            # Parse video formats and capabilities
            formats = self._parse_video_capabilities(result.stderr)
            device.video_formats = formats.get("formats", [])
            device.max_resolution = formats.get("max_resolution")
            device.max_fps = formats.get("max_fps")
            
        except Exception as e:
            self.logger.warning("Failed to enrich video device info", 
                              device=device.name, error=str(e))
            device.status = DeviceStatus.ERROR
    
    async def _enrich_audio_device_info(self, device: DeviceInfo) -> None:
        """Get additional information about an audio device."""
        try:
            # Query device capabilities using FFmpeg
            cmd = [
                "ffmpeg", "-f", "dshow",
                "-list_options", "true", 
                "-i", f"audio={device.name}"
            ]
            
            result = await self._run_command(cmd)
            
            # Parse audio formats and capabilities  
            formats = self._parse_audio_capabilities(result.stderr)
            device.audio_formats = formats.get("formats", [])
            
        except Exception as e:
            self.logger.warning("Failed to enrich audio device info",
                              device=device.name, error=str(e))
            device.status = DeviceStatus.ERROR
    
    def _parse_video_capabilities(self, ffmpeg_output: str) -> Dict[str, Any]:
        """Parse FFmpeg output to extract video capabilities."""
        capabilities = {
            "formats": [],
            "max_resolution": None,
            "max_fps": None
        }
        
        try:
            # Look for supported formats and resolutions
            # Example: [dshow @ 000001]   vcodec=mjpeg  min s=160x120 fps=30 max s=1920x1080 fps=30
            format_pattern = r'vcodec=(\w+).*?min s=(\d+x\d+).*?max s=(\d+x\d+).*?fps=(\d+)'
            
            matches = re.findall(format_pattern, ffmpeg_output)
            
            max_width, max_height, max_fps = 0, 0, 0
            
            for codec, min_res, max_res, fps in matches:
                capabilities["formats"].append({
                    "codec": codec,
                    "min_resolution": min_res,
                    "max_resolution": max_res,
                    "fps": int(fps)
                })
                
                # Track maximum capabilities
                width, height = map(int, max_res.split('x'))
                if width * height > max_width * max_height:
                    max_width, max_height = width, height
                    capabilities["max_resolution"] = max_res
                    
                max_fps = max(max_fps, int(fps))
                
            capabilities["max_fps"] = max_fps if max_fps > 0 else None
            
        except Exception as e:
            self.logger.warning("Failed to parse video capabilities", error=str(e))
            
        return capabilities
    
    def _parse_audio_capabilities(self, ffmpeg_output: str) -> Dict[str, Any]:
        """Parse FFmpeg output to extract audio capabilities."""
        capabilities = {
            "formats": []
        }
        
        try:
            # Look for supported audio formats
            # Example: [dshow @ 000001]   acodec=pcm_s16le  sample_rate=44100  channels=2
            format_pattern = r'acodec=(\w+).*?sample_rate=(\d+).*?channels=(\d+)'
            
            matches = re.findall(format_pattern, ffmpeg_output)
            
            for codec, sample_rate, channels in matches:
                capabilities["formats"].append({
                    "codec": codec,
                    "sample_rate": int(sample_rate),
                    "channels": int(channels)
                })
                
        except Exception as e:
            self.logger.warning("Failed to parse audio capabilities", error=str(e))
            
        return capabilities
    
    async def _run_command(self, cmd: List[str], timeout: int = 10) -> subprocess.CompletedProcess:
        """Run a command asynchronously with timeout."""
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return subprocess.CompletedProcess(
                cmd,
                process.returncode,
                stdout.decode('utf-8', errors='ignore'),
                stderr.decode('utf-8', errors='ignore')
            )
            
        except asyncio.TimeoutError:
            self.logger.warning("Command timed out", command=" ".join(cmd))
            raise
        except Exception as e:
            self.logger.error("Command execution failed", command=" ".join(cmd), error=str(e))
            raise
    
    async def validate_device(self, device_name: str, device_type: DeviceType) -> Tuple[bool, str]:
        """
        Validate that a specific device is available and working.
        
        Args:
            device_name: Name of the device to validate
            device_type: Type of device (video/audio)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.logger.info("Validating device", device=device_name, type=device_type.value)
            
            if device_type == DeviceType.VIDEO:
                return await self._validate_video_device(device_name)
            elif device_type == DeviceType.AUDIO:
                return await self._validate_audio_device(device_name)
            else:
                return False, "Invalid device type"
                
        except Exception as e:
            error_msg = f"Device validation failed: {str(e)}"
            self.logger.error("Device validation error", device=device_name, error=error_msg)
            return False, error_msg
    
    async def _validate_video_device(self, device_name: str) -> Tuple[bool, str]:
        """Validate a video device by attempting a test capture."""
        try:
            # Test capture for 2 seconds to validate device
            cmd = [
                "ffmpeg", "-f", "dshow",
                "-i", f"video={device_name}",
                "-t", "2",  # Capture for 2 seconds
                "-f", "null", "-"  # Discard output
            ]
            
            result = await self._run_command(cmd, timeout=15)
            
            if result.returncode == 0:
                return True, "Device validated successfully"
            else:
                error_msg = f"FFmpeg validation failed: {result.stderr}"
                return False, error_msg
                
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    async def _validate_audio_device(self, device_name: str) -> Tuple[bool, str]:
        """Validate an audio device by attempting a test capture."""
        try:
            # Test capture for 2 seconds to validate device
            cmd = [
                "ffmpeg", "-f", "dshow",
                "-i", f"audio={device_name}",
                "-t", "2",  # Capture for 2 seconds
                "-f", "null", "-"  # Discard output
            ]
            
            result = await self._run_command(cmd, timeout=15)
            
            if result.returncode == 0:
                return True, "Device validated successfully"
            else:
                error_msg = f"FFmpeg validation failed: {result.stderr}"
                return False, error_msg
                
        except Exception as e:
            return False, f"Validation error: {str(e)}"
    
    async def get_recommended_devices(self) -> Dict[str, DeviceInfo]:
        """
        Get recommended video and audio devices based on capabilities.
        
        Returns:
            Dictionary with 'video' and 'audio' keys containing recommended devices
        """
        try:
            devices = await self.discover_devices()
            
            video_devices = [d for d in devices if d.device_type == DeviceType.VIDEO and d.status == DeviceStatus.AVAILABLE]
            audio_devices = [d for d in devices if d.device_type == DeviceType.AUDIO and d.status == DeviceStatus.AVAILABLE]
            
            recommended = {}
            
            # Select best video device (highest resolution)
            if video_devices:
                best_video = max(video_devices, key=lambda d: self._get_video_quality_score(d))
                recommended["video"] = best_video
                
            # Select best audio device (prefer USB devices)
            if audio_devices:
                best_audio = max(audio_devices, key=lambda d: self._get_audio_quality_score(d))
                recommended["audio"] = best_audio
                
            self.logger.info("Recommended devices selected", 
                           video=recommended.get("video", {}).get("name"),
                           audio=recommended.get("audio", {}).get("name"))
            
            return recommended
            
        except Exception as e:
            self.logger.error("Failed to get recommended devices", error=str(e))
            return {}
    
    def _get_video_quality_score(self, device: DeviceInfo) -> int:
        """Calculate a quality score for video device ranking."""
        score = 0
        
        # Prefer devices with higher resolution
        if device.max_resolution:
            try:
                width, height = map(int, device.max_resolution.split('x'))
                score += width * height
            except ValueError:
                pass
                
        # Prefer devices with higher frame rates
        if device.max_fps:
            score += device.max_fps * 1000
            
        # Prefer USB devices (often have "USB" in name)
        if "USB" in device.name.upper():
            score += 50000
            
        return score
    
    def _get_audio_quality_score(self, device: DeviceInfo) -> int:
        """Calculate a quality score for audio device ranking."""
        score = 0
        
        # Prefer USB devices
        if "USB" in device.name.upper():
            score += 1000
            
        # Prefer devices with "microphone" in name
        if "MICROPHONE" in device.name.upper():
            score += 500
            
        # Prefer devices that support higher sample rates
        if device.audio_formats:
            max_sample_rate = max(fmt.get("sample_rate", 0) for fmt in device.audio_formats)
            score += max_sample_rate // 100
            
        return score
    
    def export_device_info(self, devices: List[DeviceInfo], format: str = "json") -> str:
        """Export device information in the specified format."""
        if format == "json":
            device_dicts = []
            for device in devices:
                device_dict = {
                    "name": device.name,
                    "type": device.device_type.value,
                    "driver": device.driver,
                    "status": device.status.value,
                    "friendly_name": device.friendly_name,
                    "device_index": device.device_index
                }
                
                if device.video_formats:
                    device_dict["video_formats"] = device.video_formats
                    device_dict["max_resolution"] = device.max_resolution
                    device_dict["max_fps"] = device.max_fps
                    
                if device.audio_formats:
                    device_dict["audio_formats"] = device.audio_formats
                    
                device_dicts.append(device_dict)
                
            return json.dumps(device_dicts, indent=2)
        else:
            raise ValueError(f"Unsupported export format: {format}")


# Convenience functions for common operations

async def get_available_cameras() -> List[DeviceInfo]:
    """Get list of available camera devices."""
    detector = DeviceDetector()
    devices = await detector.discover_devices(DeviceType.VIDEO)
    return [d for d in devices if d.status == DeviceStatus.AVAILABLE]


async def get_available_microphones() -> List[DeviceInfo]:
    """Get list of available microphone devices."""
    detector = DeviceDetector()
    devices = await detector.discover_devices(DeviceType.AUDIO)
    return [d for d in devices if d.status == DeviceStatus.AVAILABLE]


async def validate_capture_setup(video_device: str, audio_device: str) -> Tuple[bool, List[str]]:
    """
    Validate a complete capture setup.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    detector = DeviceDetector()
    errors = []
    
    # Validate video device
    video_valid, video_error = await detector.validate_device(video_device, DeviceType.VIDEO)
    if not video_valid:
        errors.append(f"Video device error: {video_error}")
        
    # Validate audio device
    audio_valid, audio_error = await detector.validate_device(audio_device, DeviceType.AUDIO)
    if not audio_valid:
        errors.append(f"Audio device error: {audio_error}")
        
    return len(errors) == 0, errors