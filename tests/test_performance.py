"""Performance and stress tests for the ArchivingTool."""

import hashlib
import tempfile
import shutil
import time
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from archiving_tool.core import ArchivingTool


class TestPerformanceAndStress:
    """Test cases for performance and stress scenarios."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
        self.tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)
        
    def test_large_number_of_files(self):
        """Test handling a large number of small files."""
        # Create many small files
        num_files = 100  # Reduced for test speed
        for i in range(num_files):
            (self.source_dir / f"file_{i:04d}.txt").write_text(f"content_{i}")
            
        # Test init performance
        start_time = time.time()
        result = self.tool.init()
        init_time = time.time() - start_time
        
        assert result is True
        assert init_time < 30  # Should complete within 30 seconds
        
        # Verify all files were processed
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == num_files
        
    def test_large_file_handling(self):
        """Test handling of large files."""
        # Create a large file (1MB)
        large_content = "A" * (1024 * 1024)  # 1MB of 'A's
        large_file = self.source_dir / "large_file.txt"
        large_file.write_text(large_content)
        
        start_time = time.time()
        result = self.tool.init()
        init_time = time.time() - start_time
        
        assert result is True
        assert init_time < 10  # Should complete within 10 seconds
        
        # Verify hash calculation
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        expected_hash = hashlib.sha256(large_content.encode()).hexdigest()
        assert manifest['files']['large_file.txt']['hash'] == expected_hash
        
    def test_deep_directory_structure(self):
        """Test handling deep directory structures."""
        # Create deep directory structure
        current_dir = self.source_dir
        for i in range(10):  # 10 levels deep
            current_dir = current_dir / f"level_{i}"
            current_dir.mkdir()
            (current_dir / f"file_at_level_{i}.txt").write_text(f"content at level {i}")
            
        result = self.tool.init()
        
        assert result is True
        
        # Verify all files were found
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == 10
        
        # Verify deep file paths
        deep_files = [path for path in manifest['files'].keys() if 'level_' in path]
        assert len(deep_files) == 10
        
    def test_mixed_file_sizes(self):
        """Test handling files of varying sizes."""
        # Create files of different sizes
        file_sizes = [10, 100, 1024, 10240, 102400]  # 10B to 100KB
        
        for i, size in enumerate(file_sizes):
            content = "X" * size
            (self.source_dir / f"file_{size}bytes.txt").write_text(content)
            
        result = self.tool.init()
        
        assert result is True
        
        # Verify all files and their sizes
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == len(file_sizes)
        
        for i, size in enumerate(file_sizes):
            filename = f"file_{size}bytes.txt"
            assert manifest['files'][filename]['size'] == size
            
    def test_concurrent_file_modifications_during_scan(self):
        """Test handling files being modified during scanning."""
        # Create initial files
        (self.source_dir / "stable.txt").write_text("stable content")
        changing_file = self.source_dir / "changing.txt"
        changing_file.write_text("initial content")
        
        def modify_file_during_scan(*args, **kwargs):
            """Mock function that modifies file during scan."""
            # Simulate file being modified during hash calculation
            if 'changing.txt' in str(args[0]):
                changing_file.write_text("modified content")
                raise OSError("File changed during read")
            return original_hash(*args, **kwargs)
            
        original_hash = self.tool._calculate_hash
        
        with patch.object(self.tool, '_calculate_hash', side_effect=modify_file_during_scan):
            result = self.tool.init()
            
        # Should handle gracefully by skipping problematic files
        assert result is True
        
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        # Only stable file should be in manifest
        assert manifest['total_files'] == 1
        assert 'stable.txt' in manifest['files']
        assert 'changing.txt' not in manifest['files']
        
    def test_memory_usage_with_large_manifest(self):
        """Test memory efficiency with large manifests."""
        # Create many files to generate large manifest
        num_files = 500  # Moderate number for test
        
        for i in range(num_files):
            subdir = self.source_dir / f"dir_{i // 100}"  # Group into subdirectories
            subdir.mkdir(exist_ok=True)
            (subdir / f"file_{i}.txt").write_text(f"content_{i}")
            
        result = self.tool.init()
        
        assert result is True
        
        # Verify manifest size is reasonable
        manifest_size = self.tool.manifest_file.stat().st_size
        assert manifest_size < 1024 * 1024  # Should be less than 1MB
        
        # Verify all files are tracked
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == num_files
        
    def test_hash_calculation_performance(self):
        """Test hash calculation performance with different chunk sizes."""
        # Create a moderately large file
        content = "Test content " * 10000  # ~130KB
        test_file = self.source_dir / "test_file.txt"
        test_file.write_text(content)
        
        chunk_sizes = [1024, 8192, 65536]  # 1KB, 8KB, 64KB
        times = []
        
        for chunk_size in chunk_sizes:
            start_time = time.time()
            hash_result = self.tool._calculate_hash(test_file, chunk_size)
            times.append(time.time() - start_time)
            
        # All chunk sizes should produce same hash
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        for chunk_size in chunk_sizes:
            hash_result = self.tool._calculate_hash(test_file, chunk_size)
            assert hash_result == expected_hash
            
        # Verify performance is reasonable (all should complete quickly)
        assert max(times) < 1.0  # Should complete within 1 second
        
    def test_progress_tracking_performance(self):
        """Test that progress tracking doesn't significantly impact performance."""
        # Create moderate number of files
        num_files = 50
        for i in range(num_files):
            (self.source_dir / f"file_{i}.txt").write_text(f"content_{i}")
            
        # Test with progress tracking (normal operation)
        start_time = time.time()
        self.tool.init()
        with_progress_time = time.time() - start_time
        
        # Test copy operation
        start_time = time.time()
        self.tool.copy()
        copy_time = time.time() - start_time
        
        # Verify reasonable performance
        assert with_progress_time < 30  # Init should complete quickly
        assert copy_time < 30  # Copy should complete quickly
        
    def test_error_recovery_performance(self):
        """Test performance of error recovery mechanisms."""
        # Create files
        (self.source_dir / "good_file.txt").write_text("good content")
        (self.source_dir / "bad_file.txt").write_text("bad content")
        
        self.tool.init()
        
        # Mock copy failure for one file
        original_copy = self.tool._copy_file_with_retry
        
        def mock_copy_with_failure(source_path, dest_path, file_info):
            if "bad_file" in str(source_path):
                return False  # Simulate failure
            return original_copy(source_path, dest_path, file_info)
            
        with patch.object(self.tool, '_copy_file_with_retry', side_effect=mock_copy_with_failure):
            start_time = time.time()
            result = self.tool.copy()
            error_recovery_time = time.time() - start_time
            
        # Should fail but not take too long
        assert result is False
        assert error_recovery_time < 10  # Should fail fast
        
    def test_manifest_loading_performance(self):
        """Test manifest loading performance with large manifests."""
        # Create large manifest
        num_files = 1000
        for i in range(num_files):
            (self.source_dir / f"file_{i:04d}.txt").write_text(f"content_{i}")
            
        self.tool.init()
        
        # Test manifest loading performance
        start_time = time.time()
        manifest = self.tool._load_manifest()
        load_time = time.time() - start_time
        
        assert manifest is not None
        assert load_time < 5  # Should load within 5 seconds
        assert len(manifest['files']) == num_files
        
    def test_verification_performance(self):
        """Test verification performance with many files."""
        # Create files
        num_files = 100
        for i in range(num_files):
            (self.source_dir / f"file_{i}.txt").write_text(f"content_{i}")
            
        self.tool.init()
        self.tool.copy()
        
        # Test verification performance
        start_time = time.time()
        result = self.tool.verify()
        verify_time = time.time() - start_time
        
        assert result is True
        assert verify_time < 30  # Should complete within 30 seconds


class TestEdgeCaseStress:
    """Stress tests for edge cases and boundary conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
        self.tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)
        
    def test_empty_files(self):
        """Test handling of empty files."""
        # Create empty files
        for i in range(10):
            (self.source_dir / f"empty_{i}.txt").touch()
            
        result = self.tool.init()
        
        assert result is True
        
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == 10
        
        # Verify empty files have expected hash
        empty_hash = hashlib.sha256(b"").hexdigest()
        for i in range(10):
            filename = f"empty_{i}.txt"
            assert manifest['files'][filename]['size'] == 0
            assert manifest['files'][filename]['hash'] == empty_hash
            
    def test_files_with_special_characters(self):
        """Test handling files with special characters in names."""
        special_names = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "file.with.dots.txt",
            "file(with)parentheses.txt",
            "file[with]brackets.txt",
            "file{with}braces.txt",
            "file'with'quotes.txt",
            "file\"with\"doublequotes.txt",
        ]
        
        for name in special_names:
            try:
                (self.source_dir / name).write_text(f"content of {name}")
            except OSError:
                # Skip names that are invalid on current filesystem
                continue
                
        result = self.tool.init()
        
        assert result is True
        
        # Copy and verify
        result = self.tool.copy()
        assert result is True
        
        result = self.tool.verify()
        assert result is True
        
    def test_very_long_filenames(self):
        """Test handling of very long filenames."""
        # Create file with long name (but within filesystem limits)
        long_name = "a" * 200 + ".txt"  # 200 character filename
        
        try:
            (self.source_dir / long_name).write_text("content")
            
            result = self.tool.init()
            assert result is True
            
            result = self.tool.copy()
            assert result is True
            
        except OSError:
            # Skip if filesystem doesn't support long names
            pytest.skip("Filesystem doesn't support long filenames")
            
    def test_rapid_file_updates(self):
        """Test handling rapid file updates."""
        test_file = self.source_dir / "rapid_update.txt"
        test_file.write_text("initial")
        
        self.tool.init()
        
        # Rapidly update file and run update
        for i in range(5):
            time.sleep(0.1)  # Small delay to ensure different mtime
            test_file.write_text(f"update_{i}")
            result = self.tool.update()
            assert result is True
            
        # Verify final state
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        final_hash = hashlib.sha256("update_4".encode()).hexdigest()
        assert manifest['files']['rapid_update.txt']['hash'] == final_hash
        
    def test_simultaneous_read_write_operations(self):
        """Test behavior during simultaneous read/write operations."""
        # Create initial files
        for i in range(10):
            (self.source_dir / f"file_{i}.txt").write_text(f"content_{i}")
            
        self.tool.init()
        
        # Simulate file being modified during copy
        def modify_during_copy(source_path, dest_path, file_info):
            if "file_5" in str(source_path):
                # Modify source during copy
                source_path.write_text("modified during copy")
                # This should cause hash mismatch and retry
                return False
            return True
            
        with patch.object(self.tool, '_copy_file_with_retry', side_effect=modify_during_copy):
            result = self.tool.copy()
            
        # Should handle gracefully
        assert result is False  # Will fail due to our mock


import json

if __name__ == "__main__":
    pytest.main([__file__])
