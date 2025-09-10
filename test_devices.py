#!/usr/bin/env python3
"""
Test the detected devices with FFmpeg validation
"""

import asyncio
import subprocess
import sys

async def test_device_validation():
    """Test if the detected devices actually work with FFmpeg."""
    
    video_device = "Anker PowerConf C200"
    audio_device = "Microphone (2- Anker PowerConf C200)"
    
    print("Testing detected devices with FFmpeg...")
    print(f"Video: {video_device}")
    print(f"Audio: {audio_device}")
    print()
    
    # Test video device
    print("Testing video device (5 second capture)...")
    try:
        cmd = [
            "ffmpeg", "-f", "dshow", 
            "-i", f"video={video_device}",
            "-t", "5",  # 5 seconds
            "-f", "null", "-",
            "-y"  # Overwrite
        ]
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            print("PASS: Video device validation successful!")
        else:
            print("FAIL: Video device validation failed:")
            print(stderr.decode('utf-8', errors='ignore')[-500:])  # Last 500 chars
            
    except Exception as e:
        print(f"ERROR: Video test error: {e}")
    
    print()
    
    # Test audio device  
    print("Testing audio device (5 second capture)...")
    try:
        cmd = [
            "ffmpeg", "-f", "dshow",
            "-i", f"audio={audio_device}",
            "-t", "5",  # 5 seconds
            "-f", "null", "-",
            "-y"  # Overwrite
        ]
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            print("PASS: Audio device validation successful!")
        else:
            print("FAIL: Audio device validation failed:")
            print(stderr.decode('utf-8', errors='ignore')[-500:])  # Last 500 chars
            
    except Exception as e:
        print(f"FAIL: Audio test error: {e}")
    
    print()
    
    # Test combined capture
    print("Testing combined audio+video capture (3 seconds)...")
    try:
        cmd = [
            "ffmpeg", "-f", "dshow",
            "-i", f"video={video_device}:audio={audio_device}",
            "-t", "3",  # 3 seconds
            "-f", "null", "-",
            "-y"  # Overwrite
        ]
        
        result = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await result.communicate()
        
        if result.returncode == 0:
            print("PASS: Combined capture validation successful!")
            print("\nSUCCESS: All device tests passed!")
            print("Your webcam capture system is ready to use.")
        else:
            print("FAIL: Combined capture validation failed:")
            print(stderr.decode('utf-8', errors='ignore')[-500:])  # Last 500 chars
            
    except Exception as e:
        print(f"FAIL: Combined test error: {e}")

if __name__ == "__main__":
    asyncio.run(test_device_validation())