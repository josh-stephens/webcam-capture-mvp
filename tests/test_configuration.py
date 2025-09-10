"""
Tests for the configuration system.
"""

import tempfile
from pathlib import Path
import yaml
import pytest

from src.main import Settings, CaptureSettings, StorageSettings, AudioSettings


class TestSettingsLoading:
    """Test configuration loading and validation."""
    
    def test_default_settings_creation(self):
        """Test creating settings with default values."""
        settings = Settings()
        
        assert settings.capture.video_device == "USB Camera"
        assert settings.capture.audio_device == "Microphone"
        assert settings.audio.sample_rate == 16000
        assert settings.storage.archive_path == "C:\\archive"
        assert settings.activation.enabled is True
        
    def test_settings_from_yaml_file(self):
        """Test loading settings from YAML configuration file."""
        config_data = {
            "capture": {
                "video_device": "Test Camera",
                "audio_device": "Test Microphone"
            },
            "audio": {
                "sample_rate": 22050,
                "whisper_model": "small"
            },
            "storage": {
                "archive_path": "/tmp/test-archive",
                "max_daily_size_gb": 5
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)
            
        try:
            settings = Settings.load_from_file(config_path)
            
            assert settings.capture.video_device == "Test Camera"
            assert settings.capture.audio_device == "Test Microphone"
            assert settings.audio.sample_rate == 22050
            assert settings.audio.whisper_model == "small"
            assert settings.storage.archive_path == "/tmp/test-archive"
            assert settings.storage.max_daily_size_gb == 5
            
            # Check defaults are preserved for unspecified values
            assert settings.audio.vad_threshold == 0.5
            assert settings.activation.enabled is True
            
        finally:
            config_path.unlink()
            
    def test_invalid_config_file_fallback(self):
        """Test that invalid config files fall back to defaults."""
        non_existent_path = Path("/non/existent/config.yaml")
        settings = Settings.load_from_file(non_existent_path)
        
        # Should fall back to defaults
        assert settings.capture.video_device == "USB Camera"
        assert settings.audio.sample_rate == 16000
        
    def test_partial_config_override(self):
        """Test that partial configuration properly overrides defaults."""
        config_data = {
            "audio": {
                "whisper_model": "large",
                "vad_threshold": 0.8
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = Path(f.name)
            
        try:
            settings = Settings.load_from_file(config_path)
            
            # Overridden values
            assert settings.audio.whisper_model == "large"
            assert settings.audio.vad_threshold == 0.8
            
            # Default values preserved
            assert settings.audio.sample_rate == 16000
            assert settings.capture.video_device == "USB Camera"
            assert settings.storage.archive_path == "C:\\archive"
            
        finally:
            config_path.unlink()


class TestConfigurationValidation:
    """Test configuration validation and constraints."""
    
    def test_audio_settings_validation(self):
        """Test audio settings validation."""
        audio = AudioSettings(
            sample_rate=16000,
            vad_threshold=0.5,
            whisper_model="base"
        )
        
        assert audio.sample_rate == 16000
        assert audio.vad_threshold == 0.5
        assert audio.whisper_model == "base"
        
    def test_storage_settings_validation(self):
        """Test storage settings validation."""
        storage = StorageSettings(
            archive_path="/tmp/archive",
            max_daily_size_gb=10,
            hot_storage_hours=48
        )
        
        assert storage.archive_path == "/tmp/archive"
        assert storage.max_daily_size_gb == 10
        assert storage.hot_storage_hours == 48
        
    def test_capture_settings_validation(self):
        """Test capture settings validation."""
        capture = CaptureSettings(
            video_device="USB Camera",
            audio_device="Microphone",
            quality="high",
            frame_rate=30,
            resolution="1920x1080"
        )
        
        assert capture.video_device == "USB Camera"
        assert capture.audio_device == "Microphone"
        assert capture.quality == "high"
        assert capture.frame_rate == 30
        assert capture.resolution == "1920x1080"


class TestVoiceActivationPhrases:
    """Test voice activation phrase configuration."""
    
    def test_default_activation_phrases(self, test_settings):
        """Test default activation phrases are properly configured."""
        activation = test_settings.activation
        
        assert "start_recording" in activation.phrases
        assert "mark_important" in activation.phrases
        assert "analyze_content" in activation.phrases
        assert "show_status" in activation.phrases
        assert "pause_recording" in activation.phrases
        
        # Check actual phrase values
        assert activation.phrases["start_recording"] == "test start recording"
        assert activation.phrases["mark_important"] == "test mark important"
        
    def test_activation_settings_parameters(self, test_settings):
        """Test activation parameter configuration."""
        activation = test_settings.activation
        
        assert activation.enabled is True
        assert activation.confidence_threshold == 0.5
        assert activation.response_timeout_sec == 1
        assert activation.cooldown_sec == 0.1


@pytest.mark.integration
class TestFullConfigurationIntegration:
    """Test full configuration integration with components."""
    
    def test_settings_integration_with_components(self, test_settings):
        """Test that settings work properly with all components."""
        # Test that settings can be used to initialize all components
        from src.storage.manager import StorageManager
        from src.audio.processor import AudioProcessor
        from src.vault.writer import VaultWriter
        
        # Should not raise any exceptions
        storage_manager = StorageManager(test_settings)
        audio_processor = AudioProcessor(test_settings)
        vault_writer = VaultWriter(test_settings)
        
        # Check that components are properly configured
        assert storage_manager.hot_storage_hours == test_settings.storage.hot_storage_hours
        assert audio_processor.settings == test_settings
        assert vault_writer.settings == test_settings
        
    def test_audio_configuration_integration(self, test_settings):
        """Test audio configuration integration."""
        from src.audio.vad import VoiceActivityDetector
        
        vad = VoiceActivityDetector(test_settings)
        
        # Should use the configured VAD model
        assert test_settings.audio.vad_model == "webrtc"
        # VAD should be initialized with correct settings
        assert vad.vad.sample_rate == test_settings.audio.sample_rate