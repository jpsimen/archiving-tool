"""Tests for the archiving tool retry functionality."""

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from archiving_tool.core import ArchivingTool


class TestRetryFunctionality(unittest.TestCase):
    """Test suite for retry functionality when drive is busy or disconnected."""
    
    def setUp(self):
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
        
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    def test_drive_accessibility_check(self):
        """Test drive accessibility checking."""
        # Normal accessible drive
        self.assertTrue(self.tool._is_drive_accessible())
        
        # Non-existent destination
        tool_bad = ArchivingTool(str(self.source_dir), "/nonexistent/path")
        self.assertFalse(tool_bad._is_drive_accessible())
        
    @patch('archiving_tool.core.ArchivingTool._is_source_accessible')
    @patch('archiving_tool.core.ArchivingTool._is_drive_accessible')
    def test_copy_with_temporary_drive_disconnect(self, mock_drive_accessible, mock_source_accessible):
        """Test copy operation with temporary drive disconnection."""
        # Source is always accessible for this test
        mock_source_accessible.return_value = True
        
        # Create a counter to control behavior
        call_count = 0
        def drive_accessible_behavior():
            nonlocal call_count
            call_count += 1
            # First call (initial check) succeeds, then a few fail, then succeed again
            if call_count == 1:
                return True  # Initial check passes
            elif call_count <= 4:
                return False  # Simulate disconnect during copy
            else:
                return True  # Recover
        
        mock_drive_accessible.side_effect = drive_accessible_behavior
        
        # Create manifest first
        self.tool.init()
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            result = self.tool.copy()
            
        self.assertTrue(result)
        self.assertTrue((self.dest_dir / "test1.txt").exists())
        self.assertTrue((self.dest_dir / "test2.txt").exists())
        
    @patch('archiving_tool.core.ArchivingTool._is_source_accessible')
    @patch('archiving_tool.core.ArchivingTool._is_drive_accessible')
    def test_copy_with_persistent_drive_disconnect(self, mock_drive_accessible, mock_source_accessible):
        """Test copy operation with persistent drive disconnection."""
        # Source is accessible but drive stays disconnected for all retry attempts
        mock_source_accessible.return_value = True
        mock_drive_accessible.return_value = False
        
        # Create manifest first
        self.tool.init()
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            result = self.tool.copy()
            
        self.assertFalse(result)
        # Files should not exist in destination
        self.assertFalse((self.dest_dir / "test1.txt").exists())
        self.assertFalse((self.dest_dir / "test2.txt").exists())
        
    @patch('shutil.copy2')
    def test_copy_with_temporary_io_error(self, mock_copy):
        """Test copy operation with temporary I/O errors."""
        # Store reference to original copy function
        original_copy = shutil.copy2.__wrapped__ if hasattr(shutil.copy2, '__wrapped__') else shutil.copy2
        
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
                # Copy the content manually to avoid recursion
                with open(src, 'rb') as src_file, open(dst, 'wb') as dst_file:
                    dst_file.write(src_file.read())
                return None
        
        mock_copy.side_effect = copy_behavior
        
        # Create manifest first
        self.tool.init()
        
        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            result = self.tool.copy()
            
        self.assertTrue(result)
        
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
            
        self.assertFalse(result)
        
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
                
        self.assertTrue(result)
        
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
        self.assertTrue(success)
        
        # Check progress file exists
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        self.assertTrue(progress_file.exists())
        
        # Load progress state
        progress_data = self.tool._load_progress_state()
        self.assertIsNotNone(progress_data)
        self.assertEqual(progress_data['completed_files'], completed_files)
        self.assertEqual(progress_data['failed_files'], failed_files)
        self.assertEqual(progress_data['manifest_snapshot'], manifest)
        
        # Clear progress state
        self.tool._clear_progress_state()
        self.assertFalse(progress_file.exists())
        
    @patch('shutil.copy2')
    def test_resume_from_interrupted_operation(self, mock_copy):
        """Test resuming from an interrupted operation."""
        # Create manifest first
        self.tool.init()
        
        # Simulate interrupted operation - first file always fails during first run
        first_run = True
        
        def copy_side_effect(src, dst):
            nonlocal first_run
            if first_run and "test1.txt" in str(src):
                raise OSError("Drive disconnected")
            else:
                # Create the file when copy succeeds to avoid verification errors
                dst_path = Path(dst)
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                with open(src, 'rb') as src_file, open(dst, 'wb') as dst_file:
                    dst_file.write(src_file.read())
            return None
            
        mock_copy.side_effect = copy_side_effect
        
        with patch('time.sleep'):  # Speed up test
            result = self.tool.copy()
            
        # Should fail and save progress
        self.assertFalse(result)
        
        # Check progress file exists
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        self.assertTrue(progress_file.exists())
        
        # Now simulate drive is back and resume
        first_run = False  # No more errors on test1.txt
        
        with patch('time.sleep'):
            result = self.tool.copy()
            
        # Should succeed this time
        self.assertTrue(result)
        
        # Progress file should be cleaned up
        self.assertFalse(progress_file.exists())
        
    def test_retry_configuration(self):
        """Test that retry configuration is properly set."""
        # Local sources get 5 retries, 3.0s delay
        self.assertEqual(self.tool.max_retries, 5)
        self.assertEqual(self.tool.retry_delay, 3.0)
        
        # Test network source configuration
        network_tool = ArchivingTool("/mnt/network_share", str(self.dest_dir))
        self.assertEqual(network_tool.max_retries, 8)  # Network sources get more retries
        self.assertEqual(network_tool.retry_delay, 5.0)  # Network sources get longer delays
        
        # Test custom configuration
        custom_tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        custom_tool.max_retries = 5
        custom_tool.retry_delay = 1.0
        
        self.assertEqual(custom_tool.max_retries, 5)
        self.assertEqual(custom_tool.retry_delay, 1.0)
        
    @patch('archiving_tool.core.ArchivingTool._copy_file_with_retry')
    def test_update_with_retry_failure(self, mock_copy_retry):
        """Test update operation with retry failures."""
        # Create initial manifest
        self.tool.init()
        
        # Add a new file
        new_file = self.source_dir / "new_file.txt"
        new_file.write_text("New content")
        
        # Mock copy failure
        mock_copy_retry.return_value = False
        
        result = self.tool.update()
        self.assertFalse(result)
        
        # Check progress file exists
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        self.assertTrue(progress_file.exists())
        
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
                
        self.assertTrue(result)
        # File should exist and have correct content
        self.assertTrue((self.dest_dir / "test1.txt").exists())
        self.assertEqual((self.dest_dir / "test1.txt").read_text(), "Test content 1")


class TestRetryIntegration(unittest.TestCase):
    """Integration tests for retry functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.source_dir = self.test_dir / "source"
        self.dest_dir = self.test_dir / "dest"
        
        # Create test directories
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
        # Create multiple test files
        for i in range(5):
            test_file = self.source_dir / f"file_{i}.txt"
            test_file.write_text(f"Content of file {i}")
            
        # Create subdirectory with files
        subdir = self.source_dir / "subdir"
        subdir.mkdir()
        for i in range(3):
            test_file = subdir / f"subfile_{i}.txt"
            test_file.write_text(f"Content of subfile {i}")
            
        self.tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
    def tearDown(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
    def test_partial_failure_and_resume(self):
        """Test partial failure during large copy and successful resume."""
        # Create manifest
        self.tool.init()
        
        # Mock copy to persistently fail on 3rd file (for all retry attempts)
        original_copy = shutil.copy2
        call_count = 0
        failed_file = None
        
        def selective_fail_copy(src, dst):
            nonlocal call_count, failed_file
            call_count += 1
            # Determine which file should fail persistently
            if call_count == 3 and failed_file is None:
                failed_file = str(src)
            
            # Always fail on the designated file
            if failed_file and str(src) == failed_file:
                raise OSError("Drive disconnected")
            return original_copy(src, dst)
            
        with patch('shutil.copy2', side_effect=selective_fail_copy):
            with patch('time.sleep'):
                result = self.tool.copy()
                
        # Should fail
        self.assertFalse(result)
        
        # Check some files were copied
        copied_files = list(self.dest_dir.rglob("*.txt"))
        self.assertGreater(len(copied_files), 0)
        self.assertLess(len(copied_files), 8)  # Not all files
        
        # Check progress file
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        self.assertTrue(progress_file.exists())
        
        # Resume operation (no more failures)
        with patch('time.sleep'):
            result = self.tool.copy()
            
        # Should succeed
        self.assertTrue(result)
        
        # All files should now be copied
        copied_files = list(self.dest_dir.rglob("*.txt"))
        self.assertEqual(len(copied_files), 8)
        
        # Progress file should be cleaned up
        self.assertFalse(progress_file.exists())


if __name__ == '__main__':
    # Run tests
    unittest.main()
