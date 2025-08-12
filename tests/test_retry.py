"""Tests for the archiving tool retry functionality."""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from archiving_tool.core import ArchivingTool


class TestRetryFunctionality:
    """Test suite for retry functionality when drive is busy or disconnected."""
    
    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.source_dir = self.test_dir / "source"
        self.dest_dir = self.test_dir / "dest"
        
        # Create test directories
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
        # Create test files
        self.test_file1 = self.source_dir / "test1.txt"
        self.test_file2 = self.source_dir / "test2.txt"
        
        self.test_file1.write_text("Test content 1")
        self.test_file2.write_text("Test content 2")
        
        # Initialize archiving tool
        self.tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)
        
    @patch('shutil.copy2')
    def test_copy_with_temporary_io_error(self, mock_copy):
        """Test copy operation with temporary I/O errors."""
        # Create a counter to control behavior
        call_count = 0
        
        def copy_behavior(src, dst):
            nonlocal call_count
            call_count += 1
            # First call fails, subsequent calls succeed
            if call_count == 1:
                raise OSError("Device busy")
            else:
                # Actually create the file when copy succeeds
                dst_path = Path(dst)
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                with open(src, 'rb') as src_file, open(dst, 'wb') as dst_file:
                    dst_file.write(src_file.read())
                return None
        
        mock_copy.side_effect = copy_behavior
        
        # Create manifest first
        self.tool.init()
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            result = self.tool.copy()
            
        assert result is True
        
    @patch('shutil.copy2')
    def test_copy_with_persistent_io_error(self, mock_copy):
        """Test copy operation with persistent I/O errors."""
        # All calls raise IOError
        mock_copy.side_effect = OSError("Device busy")
        
        # Create manifest first
        self.tool.init()
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            result = self.tool.copy()
            
        assert result is False
        
    def test_hash_mismatch_retry(self):
        """Test retry when hash verification fails."""
        # Create manifest first
        self.tool.init()
        
        # Mock hash calculation to fail first time, succeed second time
        original_calc_hash = self.tool._calculate_hash
        call_count = 0
        
        def mock_calc_hash(file_path):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First two calls (during copy verification)
                return "wrong_hash"
            return original_calc_hash(file_path)
            
        with patch.object(self.tool, '_calculate_hash', side_effect=mock_calc_hash):
            with patch('time.sleep'):  # Speed up test
                result = self.tool.copy()
                
        assert result is True
        
    def test_progress_state_saving_and_loading(self):
        """Test saving and loading progress state."""
        # Create manifest first
        self.tool.init()
        
        # Test data
        manifest = {"test": "data"}
        completed_files = ["file1.txt", "file2.txt"]
        failed_files = ["file3.txt"]
        
        # Save progress state
        success = self.tool._save_progress_state(manifest, completed_files, failed_files)
        assert success is True
        
        # Check progress file exists
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        assert progress_file.exists()
        
        # Load progress state
        progress_data = self.tool._load_progress_state()
        assert progress_data is not None
        assert progress_data['completed_files'] == completed_files
        assert progress_data['failed_files'] == failed_files
        assert progress_data['manifest_snapshot'] == manifest
        
        # Clear progress state
        self.tool._clear_progress_state()
        assert not progress_file.exists()
        
    def test_file_cleanup_on_retry(self):
        """Test that partial files are cleaned up on retry."""
        # Create manifest first
        self.tool.init()
        
        # Create a partial file that would be cleaned up
        partial_file = self.dest_dir / "test1.txt"
        partial_file.write_text("partial content")
        
        # Mock copy to fail, then check file is removed
        original_copy = shutil.copy2
        call_count = 0
        
        def mock_copy_with_cleanup(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Create partial file then fail
                Path(dst).write_text("corrupted")
                raise OSError("Drive busy")
            else:
                # Succeed on retry
                return original_copy(src, dst)
                
        with patch('shutil.copy2', side_effect=mock_copy_with_cleanup):
            with patch('time.sleep'):  # Speed up test
                result = self.tool.copy()
                
        assert result is True
        # File should exist and have correct content
        assert (self.dest_dir / "test1.txt").exists()
        assert (self.dest_dir / "test1.txt").read_text() == "Test content 1"
