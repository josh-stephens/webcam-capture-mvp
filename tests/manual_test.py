"""
Manual Test Script

A simple script to manually test the webcam capture system 
with real hardware devices.
"""

import asyncio
import sys
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import Settings, WebcamCaptureApp
from utils.device_detection import DeviceDetector, DeviceType, validate_capture_setup


async def test_device_discovery():
    """Test device discovery functionality."""
    print("🔍 Testing Device Discovery...")
    print("=" * 50)
    
    detector = DeviceDetector()
    
    try:
        # Discover all devices
        devices = await detector.discover_devices(DeviceType.BOTH)
        
        if not devices:
            print("❌ No devices found")
            return False
            
        print(f"✅ Found {len(devices)} devices:")
        
        for i, device in enumerate(devices, 1):
            print(f"\n{i}. {device.name}")
            print(f"   Type: {device.device_type.value}")
            print(f"   Status: {device.status.value}")
            
            if device.max_resolution:
                print(f"   Max Resolution: {device.max_resolution}")
            if device.max_fps:
                print(f"   Max FPS: {device.max_fps}")
                
        return True
        
    except Exception as e:
        print(f"❌ Device discovery failed: {e}")
        return False


async def test_device_validation(video_device: str, audio_device: str):
    """Test device validation."""
    print(f"\n🔧 Testing Device Validation...")
    print("=" * 50)
    
    try:
        is_valid, errors = await validate_capture_setup(video_device, audio_device)
        
        if is_valid:
            print("✅ Device validation successful!")
            return True
        else:
            print("❌ Device validation failed:")
            for error in errors:
                print(f"  • {error}")
            return False
            
    except Exception as e:
        print(f"❌ Device validation error: {e}")
        return False


async def test_configuration_loading():
    """Test configuration loading."""
    print(f"\n⚙️ Testing Configuration Loading...")
    print("=" * 50)
    
    try:
        # Try to load default configuration
        config_path = Path(__file__).parent.parent / "config" / "default.yaml"
        
        if config_path.exists():
            settings = Settings.load_from_file(config_path)
            print("✅ Configuration loaded from default.yaml")
        else:
            settings = Settings()
            print("✅ Using default configuration (no config file found)")
            
        print(f"Video Device: {settings.capture.video_device}")
        print(f"Audio Device: {settings.capture.audio_device}")
        print(f"Archive Path: {settings.storage.archive_path}")
        print(f"Whisper Model: {settings.audio.whisper_model}")
        
        return settings
        
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return None


async def test_audio_processor_init(settings: Settings):
    """Test audio processor initialization."""
    print(f"\n🎵 Testing Audio Processor Initialization...")
    print("=" * 50)
    
    try:
        from audio.processor import AudioProcessor
        
        processor = AudioProcessor(settings)
        
        # Test VAD initialization
        await processor.vad.initialize()
        print("✅ VAD initialized successfully")
        
        # Test Whisper loading (this may take time)
        print("Loading Whisper model (this may take a moment)...")
        await processor._load_whisper_model()
        
        if processor._whisper_model:
            print("✅ Whisper model loaded successfully")
        else:
            print("⚠️  Whisper model not loaded")
            
        await processor.vad.cleanup()
        return True
        
    except Exception as e:
        print(f"❌ Audio processor initialization failed: {e}")
        return False


async def test_storage_manager_init(settings: Settings):
    """Test storage manager initialization."""
    print(f"\n💾 Testing Storage Manager...")
    print("=" * 50)
    
    try:
        from storage.manager import StorageManager
        
        manager = StorageManager(settings)
        await manager.start()
        
        print("✅ Storage manager initialized")
        print(f"Hot Storage: {manager.hot_storage}")
        print(f"Warm Storage: {manager.warm_storage}")  
        print(f"Cold Storage: {manager.cold_storage}")
        
        # Test storage metrics
        metrics = manager.get_storage_metrics()
        print(f"Storage Metrics: {metrics}")
        
        await manager.stop()
        return True
        
    except Exception as e:
        print(f"❌ Storage manager test failed: {e}")
        return False


async def test_vault_integration(settings: Settings):
    """Test vault integration."""
    print(f"\n📝 Testing Vault Integration...")
    print("=" * 50)
    
    try:
        from vault.writer import VaultWriter
        from datetime import datetime
        
        writer = VaultWriter(settings)
        
        # Test system event logging
        await writer.write_system_event(
            event_type="test",
            description="Manual test system event",
            metadata={"test_run": True}
        )
        print("✅ System event logged")
        
        # Test transcription logging
        await writer.write_transcription(
            text="This is a test transcription from manual testing",
            timestamp=datetime.now(),
            confidence=0.95,
            is_activation=False,
            activation_command=None
        )
        print("✅ Transcription logged")
        
        # Check if daily note was created
        today = datetime.now().date()
        daily_note = writer.daily_notes_path / f"{today}.md"
        
        if daily_note.exists():
            print(f"✅ Daily note created: {daily_note}")
            
            # Show a snippet of the content
            content = daily_note.read_text()
            lines = content.split('\n')[:10]
            print("Daily note preview:")
            for line in lines:
                print(f"  {line}")
        else:
            print("⚠️  Daily note not found")
            
        return True
        
    except Exception as e:
        print(f"❌ Vault integration test failed: {e}")
        return False


async def run_quick_capture_test(settings: Settings, duration: int = 5):
    """Run a quick capture test."""
    print(f"\n🎥 Running Quick Capture Test ({duration}s)...")
    print("=" * 50)
    print("⚠️  This will attempt to access your webcam and microphone!")
    
    try:
        app = WebcamCaptureApp(settings)
        
        print("Starting capture system...")
        
        # Start the app in background
        app_task = asyncio.create_task(app.start())
        
        # Wait for specified duration
        await asyncio.sleep(duration)
        
        print("Stopping capture system...")
        app.shutdown_event.set()
        
        # Wait for app to stop
        try:
            await asyncio.wait_for(app_task, timeout=10)
        except asyncio.TimeoutError:
            print("⚠️  App took too long to stop")
            
        await app.stop()
        
        print("✅ Quick capture test completed")
        return True
        
    except Exception as e:
        print(f"❌ Capture test failed: {e}")
        return False


async def main():
    """Run all manual tests."""
    print("🚀 Webcam Capture MVP - Manual Test Suite")
    print("=" * 60)
    
    results = {}
    
    # Test device discovery
    results["device_discovery"] = await test_device_discovery()
    
    # Test configuration
    settings = await test_configuration_loading()
    if not settings:
        print("\n❌ Cannot continue without valid configuration")
        return
        
    results["configuration"] = True
    
    # Test device validation
    results["device_validation"] = await test_device_validation(
        settings.capture.video_device,
        settings.capture.audio_device
    )
    
    # Test storage manager
    results["storage_manager"] = await test_storage_manager_init(settings)
    
    # Test vault integration  
    results["vault_integration"] = await test_vault_integration(settings)
    
    # Test audio processor (optional, can be slow)
    print("\n🤔 Test audio processor initialization? (may take time for Whisper download)")
    response = input("Enter 'y' to test audio processor: ").lower().strip()
    
    if response == 'y':
        results["audio_processor"] = await test_audio_processor_init(settings)
    
    # Quick capture test (optional)
    print("\n🤔 Run quick capture test? (will access camera/microphone)")
    response = input("Enter 'y' to run capture test: ").lower().strip()
    
    if response == 'y':
        results["capture_test"] = await run_quick_capture_test(settings, duration=3)
    
    # Summary
    print("\n📊 Test Results Summary")
    print("=" * 30)
    
    passed = 0
    total = 0
    
    for test_name, result in results.items():
        total += 1
        if result:
            passed += 1
            print(f"✅ {test_name}: PASSED")
        else:
            print(f"❌ {test_name}: FAILED")
            
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! System appears to be working correctly.")
    else:
        print("⚠️  Some tests failed. Check error messages above.")
        
    print("\n💡 Next steps:")
    print("  • Run: python src/main.py --help")
    print("  • Run: python src/utils/device_cli.py discover")
    print("  • Check configuration in config/default.yaml")


if __name__ == "__main__":
    asyncio.run(main())