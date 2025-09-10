"""
Device Detection CLI Tool

Command-line utility for discovering and validating USB devices.
Useful for troubleshooting and device selection.
"""

import asyncio
import sys
from pathlib import Path

import typer
import structlog

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.device_detection import DeviceDetector, DeviceType, validate_capture_setup


app = typer.Typer(help="USB Device Detection and Validation Tool")


@app.command()
def discover(
    device_type: str = typer.Option(
        "both", 
        "--type", 
        "-t",
        help="Device type to discover: video, audio, or both"
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f", 
        help="Output format: table or json"
    ),
    validate: bool = typer.Option(
        False,
        "--validate",
        "-v",
        help="Validate discovered devices"
    )
):
    """Discover available USB audio/video devices."""
    
    async def run_discovery():
        # Setup logging
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        detector = DeviceDetector()
        
        # Parse device type
        if device_type.lower() == "video":
            dt = DeviceType.VIDEO
        elif device_type.lower() == "audio":
            dt = DeviceType.AUDIO
        elif device_type.lower() == "both":
            dt = DeviceType.BOTH
        else:
            typer.echo(f"Invalid device type: {device_type}")
            raise typer.Exit(1)
            
        typer.echo(f"Discovering {device_type} devices...")
        devices = await detector.discover_devices(dt)
        
        if not devices:
            typer.echo("No devices found.")
            return
            
        if validate:
            typer.echo("Validating devices...")
            for device in devices:
                is_valid, error = await detector.validate_device(device.name, device.device_type)
                if not is_valid:
                    device.status = device.status  # Keep original status
                    typer.echo(f"⚠️  {device.name}: {error}")
                else:
                    typer.echo(f"✅ {device.name}: Validated successfully")
        
        if output_format == "json":
            output = detector.export_device_info(devices, "json")
            typer.echo(output)
        else:
            # Table format
            typer.echo("\n📱 Discovered Devices:")
            typer.echo("=" * 80)
            
            for i, device in enumerate(devices, 1):
                typer.echo(f"\n{i}. {device.name}")
                typer.echo(f"   Type: {device.device_type.value}")
                typer.echo(f"   Status: {device.status.value}")
                typer.echo(f"   Driver: {device.driver}")
                
                if device.max_resolution:
                    typer.echo(f"   Max Resolution: {device.max_resolution}")
                if device.max_fps:
                    typer.echo(f"   Max FPS: {device.max_fps}")
                if device.video_formats:
                    formats = [f"{fmt.get('codec', 'unknown')}" for fmt in device.video_formats]
                    typer.echo(f"   Video Formats: {', '.join(formats)}")
                if device.audio_formats:
                    formats = [f"{fmt.get('codec', 'unknown')}@{fmt.get('sample_rate', 'unknown')}Hz" for fmt in device.audio_formats]
                    typer.echo(f"   Audio Formats: {', '.join(formats)}")
    
    asyncio.run(run_discovery())


@app.command()
def validate_device(
    device_name: str = typer.Argument(..., help="Name of the device to validate"),
    device_type: str = typer.Argument(..., help="Device type: video or audio")
):
    """Validate a specific device."""
    
    async def run_validation():
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        detector = DeviceDetector()
        
        # Parse device type
        if device_type.lower() == "video":
            dt = DeviceType.VIDEO
        elif device_type.lower() == "audio":
            dt = DeviceType.AUDIO
        else:
            typer.echo(f"Invalid device type: {device_type}")
            raise typer.Exit(1)
            
        typer.echo(f"Validating {device_type} device: {device_name}")
        
        is_valid, error = await detector.validate_device(device_name, dt)
        
        if is_valid:
            typer.echo("✅ Device validation successful!")
        else:
            typer.echo(f"❌ Device validation failed: {error}")
            raise typer.Exit(1)
    
    asyncio.run(run_validation())


@app.command()
def validate_setup(
    video_device: str = typer.Argument(..., help="Video device name"),
    audio_device: str = typer.Argument(..., help="Audio device name")
):
    """Validate a complete capture setup with video and audio devices."""
    
    async def run_setup_validation():
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        typer.echo(f"Validating capture setup:")
        typer.echo(f"  Video: {video_device}")
        typer.echo(f"  Audio: {audio_device}")
        
        is_valid, errors = await validate_capture_setup(video_device, audio_device)
        
        if is_valid:
            typer.echo("✅ Capture setup validation successful!")
        else:
            typer.echo("❌ Capture setup validation failed:")
            for error in errors:
                typer.echo(f"  • {error}")
            raise typer.Exit(1)
    
    asyncio.run(run_setup_validation())


@app.command()
def recommend():
    """Get recommended devices for optimal capture quality."""
    
    async def run_recommendations():
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        detector = DeviceDetector()
        
        typer.echo("Analyzing devices for recommendations...")
        recommended = await detector.get_recommended_devices()
        
        if not recommended:
            typer.echo("No suitable devices found for recommendations.")
            return
            
        typer.echo("\n🎯 Recommended Devices:")
        typer.echo("=" * 50)
        
        if "video" in recommended:
            video = recommended["video"]
            typer.echo(f"\n📹 Video Device: {video.name}")
            if video.max_resolution:
                typer.echo(f"   Max Resolution: {video.max_resolution}")
            if video.max_fps:
                typer.echo(f"   Max FPS: {video.max_fps}")
                
        if "audio" in recommended:
            audio = recommended["audio"]
            typer.echo(f"\n🎤 Audio Device: {audio.name}")
            if audio.audio_formats:
                max_sample_rate = max(fmt.get("sample_rate", 0) for fmt in audio.audio_formats)
                typer.echo(f"   Max Sample Rate: {max_sample_rate}Hz")
                
        # Generate configuration snippet
        typer.echo("\n📝 Configuration snippet for default.yaml:")
        typer.echo("capture:")
        if "video" in recommended:
            typer.echo(f'  video_device: "{recommended["video"].name}"')
        if "audio" in recommended:
            typer.echo(f'  audio_device: "{recommended["audio"].name}"')
    
    asyncio.run(run_recommendations())


@app.command()
def test_ffmpeg():
    """Test if FFmpeg is available and working."""
    
    async def run_ffmpeg_test():
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer()
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        detector = DeviceDetector()
        
        typer.echo("Testing FFmpeg availability...")
        
        try:
            cmd = ["ffmpeg", "-version"]
            result = await detector._run_command(cmd, timeout=5)
            
            if result.returncode == 0:
                # Extract version info
                version_line = result.stdout.split('\n')[0]
                typer.echo(f"✅ FFmpeg is available: {version_line}")
                
                # Test DirectShow support
                typer.echo("Testing DirectShow support...")
                cmd = ["ffmpeg", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
                result = await detector._run_command(cmd, timeout=10)
                
                if "DirectShow" in result.stderr:
                    typer.echo("✅ DirectShow support confirmed")
                else:
                    typer.echo("⚠️  DirectShow support unclear")
                    
            else:
                typer.echo(f"❌ FFmpeg test failed: {result.stderr}")
                raise typer.Exit(1)
                
        except Exception as e:
            typer.echo(f"❌ FFmpeg not available: {str(e)}")
            typer.echo("\nTo install FFmpeg on Windows:")
            typer.echo("  winget install FFmpeg")
            typer.echo("  or download from: https://ffmpeg.org/download.html")
            raise typer.Exit(1)
    
    asyncio.run(run_ffmpeg_test())


if __name__ == "__main__":
    app()