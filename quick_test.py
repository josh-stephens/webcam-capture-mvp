#!/usr/bin/env python3
"""
Quick test script to validate basic system functionality
"""

import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_ffmpeg_devices():
    """Test FFmpeg device discovery"""
    print("Testing FFmpeg device discovery...")
    
    try:
        from utils.device_detection import DeviceDetector, DeviceType
        
        detector = DeviceDetector()
        devices = await detector.discover_devices(DeviceType.BOTH)
        
        print(f"Found {len(devices)} devices:")
        for device in devices:
            print(f"  - {device.name} ({device.device_type.value})")
            
        return True
        
    except Exception as e:
        print(f"Device discovery failed: {e}")
        return False

def test_configuration():
    """Test configuration loading"""
    print("\nTesting configuration system...")
    
    try:
        from main import Settings
        
        settings = Settings()
        print(f"Default video device: {settings.capture.video_device}")
        print(f"Default audio device: {settings.capture.audio_device}")
        print(f"Sample rate: {settings.audio.sample_rate}")
        print(f"Archive path: {settings.storage.archive_path}")
        
        return True
        
    except Exception as e:
        print(f"Configuration test failed: {e}")
        return False

def test_vault_integration():
    """Test vault integration basics"""
    print("\nTesting vault integration...")
    
    try:
        from vault.writer import VaultWriter
        from main import Settings
        
        settings = Settings()
        writer = VaultWriter(settings)
        
        print(f"Vault path: {writer.vault_path}")
        print(f"Daily notes path: {writer.daily_notes_path}")
        
        # Check if directories can be created
        writer.daily_notes_path.mkdir(parents=True, exist_ok=True)
        print("PASS: Vault directories accessible")
        
        return True
        
    except Exception as e:
        print(f"Vault integration test failed: {e}")
        return False

def test_audio_processor_init():
    """Test audio processor initialization"""
    print("\nTesting audio processor initialization...")
    
    try:
        from audio.processor import AudioProcessor
        from main import Settings
        
        settings = Settings()
        processor = AudioProcessor(settings)
        
        print(f"Activation phrases: {len(processor.activation_phrases)}")
        print(f"Audio buffer max length: {processor.audio_buffer.maxlen}")
        
        return True
        
    except Exception as e:
        print(f"Audio processor test failed: {e}")
        return False

async def main():
    """Run all quick tests"""
    print("Webcam Capture MVP - Quick Test Suite")
    print("=" * 50)
    
    results = []
    
    # Test configuration
    results.append(("Configuration", test_configuration()))
    
    # Test vault integration
    results.append(("Vault Integration", test_vault_integration()))
    
    # Test audio processor
    results.append(("Audio Processor", test_audio_processor_init()))
    
    # Test device discovery
    results.append(("Device Discovery", await test_ffmpeg_devices()))
    
    # Summary
    print(f"\nTest Results")
    print("=" * 30)
    
    passed = 0
    for name, result in results:
        if result:
            print(f"PASS: {name}")
            passed += 1
        else:
            print(f"FAIL: {name}")
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\nAll basic tests passed!")
        print("The system appears ready for configuration with your devices.")
        print("\nDetected devices above - update config/default.yaml with:")
        print("capture:")
        print('  video_device: "Anker PowerConf C200"')  # From FFmpeg output
        print('  audio_device: "Microphone (2- Anker PowerConf C200)"')
    else:
        print(f"\n{len(results) - passed} tests failed.")

if __name__ == "__main__":
    asyncio.run(main())