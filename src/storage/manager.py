"""
Storage Management Module

Handles three-tier storage architecture with intelligent pruning:
- Hot storage: Recent content on fast storage (48 hours)
- Warm storage: Compressed content on slower storage (30 days)  
- Cold storage: Long-term archive with high compression (years)
"""

import asyncio
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json

import structlog
from typing import Any


class StorageManager:
    """Three-tier storage with intelligent pruning."""
    
    def __init__(self, settings: Any):
        self.settings = settings
        self.logger = structlog.get_logger()
        
        # Storage directories
        self.base_path = Path(settings.storage.archive_path)
        self.hot_storage = self.base_path / "hot"
        self.warm_storage = self.base_path / "warm"
        self.cold_storage = self.base_path / "cold"
        
        # Metadata storage
        self.metadata_path = self.base_path / "metadata"
        
        # Create directory structure
        for path in [self.hot_storage, self.warm_storage, self.cold_storage, self.metadata_path]:
            path.mkdir(parents=True, exist_ok=True)
            
        # Pruning configuration
        self.hot_storage_hours = settings.storage.hot_storage_hours
        self.warm_storage_days = settings.storage.warm_storage_days
        self.cold_storage_years = settings.storage.cold_storage_years
        
        # State management
        self.is_running = False
        self.pruning_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "files_stored": 0,
            "files_pruned": 0,
            "bytes_stored": 0,
            "bytes_pruned": 0,
            "compression_ratio": 0
        }
        
    async def start(self) -> None:
        """Start the storage manager."""
        if self.is_running:
            return
            
        try:
            self.logger.info("Starting storage manager",
                           hot_storage=str(self.hot_storage),
                           warm_storage=str(self.warm_storage),
                           cold_storage=str(self.cold_storage))
            
            self.is_running = True
            
            # Start pruning task
            self.pruning_task = asyncio.create_task(self._pruning_loop())
            
            self.logger.info("Storage manager started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start storage manager", error=str(e))
            raise
            
    async def stop(self) -> None:
        """Stop the storage manager."""
        if not self.is_running:
            return
            
        try:
            self.logger.info("Stopping storage manager")
            
            self.is_running = False
            
            # Cancel pruning task
            if self.pruning_task:
                self.pruning_task.cancel()
                try:
                    await self.pruning_task
                except asyncio.CancelledError:
                    pass
                    
            self.logger.info("Storage manager stopped")
            
        except Exception as e:
            self.logger.error("Error stopping storage manager", error=str(e))
            
    async def store_video(self, video_path: Path, metadata: Dict[str, Any]) -> str:
        """Store video file with metadata tagging."""
        try:
            if not video_path.exists():
                raise FileNotFoundError(f"Video file not found: {video_path}")
                
            # Generate unique ID
            file_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{video_path.stem}"
            
            # Store in hot storage initially
            hot_file_path = self.hot_storage / f"{file_id}.mp4"
            
            # Copy or move file
            shutil.copy2(video_path, hot_file_path)
            
            # Store metadata
            metadata_file = self.metadata_path / f"{file_id}.json"
            full_metadata = {
                "file_id": file_id,
                "original_path": str(video_path),
                "stored_timestamp": datetime.now().isoformat(),
                "storage_tier": "hot",
                "file_size": hot_file_path.stat().st_size,
                "metadata": metadata
            }
            
            with open(metadata_file, 'w') as f:
                json.dump(full_metadata, f, indent=2)
                
            # Update statistics
            self.stats["files_stored"] += 1
            self.stats["bytes_stored"] += full_metadata["file_size"]
            
            self.logger.info("Video stored successfully",
                           file_id=file_id,
                           size_mb=full_metadata["file_size"] / 1024 / 1024,
                           storage_tier="hot")
            
            return file_id
            
        except Exception as e:
            self.logger.error("Failed to store video", error=str(e), video_path=str(video_path))
            raise
            
    async def mark_important(self, file_id: str, importance_level: str = "high") -> None:
        """Mark content as important to prevent pruning."""
        try:
            metadata_file = self.metadata_path / f"{file_id}.json"
            
            if not metadata_file.exists():
                raise FileNotFoundError(f"Metadata not found for file: {file_id}")
                
            # Load existing metadata
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                
            # Update importance
            metadata["importance"] = importance_level
            metadata["marked_important_at"] = datetime.now().isoformat()
            
            # Save updated metadata
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
                
            self.logger.info("Content marked as important",
                           file_id=file_id,
                           importance_level=importance_level)
            
        except Exception as e:
            self.logger.error("Failed to mark content as important", 
                            error=str(e), file_id=file_id)
            
    async def _pruning_loop(self) -> None:
        """Main pruning loop that runs periodically."""
        
        while self.is_running:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                self.logger.info("Starting storage pruning cycle")
                
                # Move files from hot to warm storage
                await self._migrate_hot_to_warm()
                
                # Move files from warm to cold storage
                await self._migrate_warm_to_cold()
                
                # Prune old content based on rules
                await self._prune_old_content()
                
                # Clean up empty directories
                await self._cleanup_empty_directories()
                
                self.logger.info("Storage pruning cycle completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Error in pruning loop", error=str(e))
                
    async def _migrate_hot_to_warm(self) -> None:
        """Migrate files from hot to warm storage."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=self.hot_storage_hours)
            
            for video_file in self.hot_storage.glob("*.mp4"):
                file_mtime = datetime.fromtimestamp(video_file.stat().st_mtime)
                
                if file_mtime < cutoff_time:
                    await self._migrate_file_to_warm(video_file)
                    
        except Exception as e:
            self.logger.error("Error migrating hot to warm storage", error=str(e))
            
    async def _migrate_file_to_warm(self, video_file: Path) -> None:
        """Migrate a single file to warm storage with compression."""
        try:
            file_id = video_file.stem
            warm_file_path = self.warm_storage / f"{file_id}_compressed.mp4"
            
            # Compress video for warm storage
            await self._compress_video(video_file, warm_file_path)
            
            # Update metadata
            metadata_file = self.metadata_path / f"{file_id}.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    
                original_size = metadata.get("file_size", 0)
                compressed_size = warm_file_path.stat().st_size
                
                metadata["storage_tier"] = "warm"
                metadata["migrated_to_warm_at"] = datetime.now().isoformat()
                metadata["compressed_size"] = compressed_size
                metadata["compression_ratio"] = compressed_size / original_size if original_size > 0 else 0
                
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
                    
            # Remove original file
            video_file.unlink()
            
            self.logger.info("File migrated to warm storage",
                           file_id=file_id,
                           original_size_mb=original_size / 1024 / 1024,
                           compressed_size_mb=compressed_size / 1024 / 1024)
            
        except Exception as e:
            self.logger.error("Failed to migrate file to warm storage", 
                            error=str(e), file_path=str(video_file))
            
    async def _compress_video(self, input_path: Path, output_path: Path) -> None:
        """Compress video for efficient storage."""
        try:
            # FFmpeg command for compression
            cmd = [
                "ffmpeg",
                "-i", str(input_path),
                "-c:v", "libx264",
                "-crf", "28",  # Higher compression
                "-preset", "slow",  # Better compression efficiency
                "-c:a", "aac",
                "-b:a", "64k",  # Lower audio bitrate
                "-y",  # Overwrite output file
                str(output_path)
            ]
            
            # Run compression in subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                raise RuntimeError(f"FFmpeg compression failed: {stderr.decode()}")
                
        except Exception as e:
            self.logger.error("Video compression failed", error=str(e))
            raise
            
    async def _migrate_warm_to_cold(self) -> None:
        """Migrate files from warm to cold storage."""
        try:
            cutoff_time = datetime.now() - timedelta(days=self.warm_storage_days)
            
            for video_file in self.warm_storage.glob("*_compressed.mp4"):
                file_mtime = datetime.fromtimestamp(video_file.stat().st_mtime)
                
                if file_mtime < cutoff_time:
                    await self._migrate_file_to_cold(video_file)
                    
        except Exception as e:
            self.logger.error("Error migrating warm to cold storage", error=str(e))
            
    async def _migrate_file_to_cold(self, video_file: Path) -> None:
        """Migrate a single file to cold storage."""
        try:
            # Simply move to cold storage (already compressed)
            cold_file_path = self.cold_storage / video_file.name
            shutil.move(str(video_file), str(cold_file_path))
            
            # Update metadata
            file_id = video_file.stem.replace("_compressed", "")
            metadata_file = self.metadata_path / f"{file_id}.json"
            
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    
                metadata["storage_tier"] = "cold"
                metadata["migrated_to_cold_at"] = datetime.now().isoformat()
                
                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)
                    
            self.logger.info("File migrated to cold storage", file_id=file_id)
            
        except Exception as e:
            self.logger.error("Failed to migrate file to cold storage", 
                            error=str(e), file_path=str(video_file))
            
    async def _prune_old_content(self) -> None:
        """Prune very old content based on retention policies."""
        try:
            cutoff_time = datetime.now() - timedelta(days=self.cold_storage_years * 365)
            
            for video_file in self.cold_storage.glob("*.mp4"):
                file_mtime = datetime.fromtimestamp(video_file.stat().st_mtime)
                
                if file_mtime < cutoff_time:
                    # Check if marked as important
                    file_id = video_file.stem.replace("_compressed", "")
                    metadata_file = self.metadata_path / f"{file_id}.json"
                    
                    should_prune = True
                    if metadata_file.exists():
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            
                        # Don't prune important content
                        if metadata.get("importance") in ["high", "critical"]:
                            should_prune = False
                            
                    if should_prune:
                        await self._prune_file(video_file, metadata_file)
                        
        except Exception as e:
            self.logger.error("Error pruning old content", error=str(e))
            
    async def _prune_file(self, video_file: Path, metadata_file: Path) -> None:
        """Prune a single file and its metadata."""
        try:
            file_size = video_file.stat().st_size
            
            # Remove files
            video_file.unlink()
            if metadata_file.exists():
                metadata_file.unlink()
                
            # Update statistics
            self.stats["files_pruned"] += 1
            self.stats["bytes_pruned"] += file_size
            
            self.logger.info("File pruned",
                           file_path=str(video_file),
                           size_mb=file_size / 1024 / 1024)
            
        except Exception as e:
            self.logger.error("Failed to prune file", error=str(e), file_path=str(video_file))
            
    async def _cleanup_empty_directories(self) -> None:
        """Clean up empty directories."""
        try:
            for storage_dir in [self.hot_storage, self.warm_storage, self.cold_storage]:
                for subdir in storage_dir.rglob("*"):
                    if subdir.is_dir() and not any(subdir.iterdir()):
                        subdir.rmdir()
                        
        except Exception as e:
            self.logger.error("Error cleaning up empty directories", error=str(e))
            
    def get_storage_metrics(self) -> Dict[str, Any]:
        """Return storage usage and health metrics."""
        try:
            # Calculate storage usage
            hot_usage = sum(f.stat().st_size for f in self.hot_storage.rglob("*") if f.is_file())
            warm_usage = sum(f.stat().st_size for f in self.warm_storage.rglob("*") if f.is_file())
            cold_usage = sum(f.stat().st_size for f in self.cold_storage.rglob("*") if f.is_file())
            
            # File counts
            hot_files = len(list(self.hot_storage.glob("*.mp4")))
            warm_files = len(list(self.warm_storage.glob("*.mp4")))
            cold_files = len(list(self.cold_storage.glob("*.mp4")))
            
            # Disk space
            total_space = shutil.disk_usage(self.base_path).total
            free_space = shutil.disk_usage(self.base_path).free
            
            return {
                "is_running": self.is_running,
                "storage_tiers": {
                    "hot": {
                        "usage_bytes": hot_usage,
                        "usage_mb": hot_usage / 1024 / 1024,
                        "file_count": hot_files,
                        "path": str(self.hot_storage)
                    },
                    "warm": {
                        "usage_bytes": warm_usage,
                        "usage_mb": warm_usage / 1024 / 1024,
                        "file_count": warm_files,
                        "path": str(self.warm_storage)
                    },
                    "cold": {
                        "usage_bytes": cold_usage,
                        "usage_mb": cold_usage / 1024 / 1024,
                        "file_count": cold_files,
                        "path": str(self.cold_storage)
                    }
                },
                "total_usage": {
                    "bytes": hot_usage + warm_usage + cold_usage,
                    "mb": (hot_usage + warm_usage + cold_usage) / 1024 / 1024,
                    "gb": (hot_usage + warm_usage + cold_usage) / 1024 / 1024 / 1024
                },
                "disk_space": {
                    "total_bytes": total_space,
                    "free_bytes": free_space,
                    "used_bytes": total_space - free_space,
                    "free_gb": free_space / 1024 / 1024 / 1024,
                    "used_percent": ((total_space - free_space) / total_space) * 100
                },
                "statistics": self.stats,
                "configuration": {
                    "hot_storage_hours": self.hot_storage_hours,
                    "warm_storage_days": self.warm_storage_days,
                    "cold_storage_years": self.cold_storage_years
                }
            }
            
        except Exception as e:
            self.logger.error("Error calculating storage metrics", error=str(e))
            return {"error": str(e)}