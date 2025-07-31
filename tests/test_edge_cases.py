"""Test cases for macOS-specific functionality and edge cases."""

import subprocess
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from archiving_tool.core import ArchivingTool


class TestMacOSSpecificFunctionality:
    """Test cases for macOS-specific features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.temp_dir) / "source"
        self.dest_dir = Path(self.temp_dir) / "dest"
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)
        
    @patch('platform.system')
    def test_is_drive_accessible_macos(self, mock_platform):
        """Test drive accessibility check on macOS."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        with patch.object(tool, '_check_macos_drive_mounted') as mock_check:
            mock_check.return_value = True
            
            result = tool._is_drive_accessible()
            
            assert result is True
            mock_check.assert_called_once()
            
    @patch('platform.system')
    def test_check_macos_drive_mounted_success(self, mock_platform):
        """Test successful macOS drive mount check."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "Device Identifier: disk2s1\nMounted: Yes\nWritable: Yes"
        
        with patch('subprocess.run', return_value=mock_result):
            result = tool._check_macos_drive_mounted()
            
            assert result is True
            
    @patch('platform.system')
    def test_check_macos_drive_mounted_failure(self, mock_platform):
        """Test failed macOS drive mount check."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        mock_result = Mock()
        mock_result.returncode = 1
        
        with patch('subprocess.run', return_value=mock_result):
            result = tool._check_macos_drive_mounted()
            
            assert result is False
            
    @patch('platform.system')
    def test_check_macos_drive_mounted_timeout(self, mock_platform):
        """Test macOS drive mount check with timeout."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('diskutil', 5)):
            result = tool._check_macos_drive_mounted()
            
            assert result is False
            
    @patch('platform.system')
    def test_detect_apfs_filesystem_success(self, mock_platform):
        """Test APFS filesystem detection."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "File System Personality: APFS\nType (Bundle): apfs"
        
        with patch('subprocess.run', return_value=mock_result):
            result = tool._detect_apfs_filesystem()
            
            assert result is True
            
    @patch('platform.system')
    def test_detect_apfs_filesystem_not_apfs(self, mock_platform):
        """Test APFS filesystem detection when not APFS."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "File System Personality: HFS+\nType (Bundle): hfs"
        
        with patch('subprocess.run', return_value=mock_result):
            result = tool._detect_apfs_filesystem()
            
            assert result is False
            
    @patch('platform.system')
    def test_optimize_for_apfs(self, mock_platform):
        """Test APFS optimization."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        with patch.object(tool, '_detect_apfs_filesystem', return_value=True):
            original_chunk_size = tool.chunk_size
            tool._optimize_for_apfs()
            
            assert tool.chunk_size == 2 * 1024 * 1024  # 2MB for APFS
            assert tool.chunk_size > original_chunk_size
            
    @patch('platform.system')
    def test_preserve_macos_metadata_success(self, mock_platform):
        """Test preserving macOS metadata."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        dest_file.write_text("content")
        
        # Mock xattr command success
        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = "com.apple.metadata:kMDItemWhereFroms\ncom.apple.quarantine"
        
        mock_copy_result = Mock()
        mock_copy_result.returncode = 0
        
        with patch('subprocess.run', side_effect=[mock_list_result, mock_copy_result]):
            result = tool._preserve_macos_metadata(source_file, dest_file)
            
            assert result is True
            
    @patch('platform.system')
    def test_preserve_macos_metadata_no_attributes(self, mock_platform):
        """Test preserving macOS metadata when no attributes exist."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        dest_file.write_text("content")
        
        # Mock xattr command with no attributes
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        
        with patch('subprocess.run', return_value=mock_result):
            result = tool._preserve_macos_metadata(source_file, dest_file)
            
            assert result is True
            
    @patch('platform.system')
    def test_copy_with_macos_optimization_success(self, mock_platform):
        """Test macOS-optimized copy operation."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        
        mock_result = Mock()
        mock_result.returncode = 0
        
        with patch('subprocess.run', return_value=mock_result):
            tool._copy_with_macos_optimization(source_file, dest_file)
            
            # Should not raise any exceptions
            
    @patch('platform.system')
    def test_copy_with_macos_optimization_fallback(self, mock_platform):
        """Test macOS-optimized copy fallback to shutil."""
        mock_platform.return_value = 'Darwin'
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(1, 'cp')):
            with patch('shutil.copy2') as mock_copy2:
                tool._copy_with_macos_optimization(source_file, dest_file)
                
                mock_copy2.assert_called_once_with(source_file, dest_file)


class TestDriveReconnectionLogic:
    """Test cases for drive reconnection and retry logic."""
    
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
        
    def test_wait_for_drive_reconnection_success(self):
        """Test successful drive reconnection."""
        with patch.object(self.tool, '_is_drive_accessible', side_effect=[False, False, True]):
            with patch('time.sleep'):  # Speed up test
                result = self.tool._wait_for_drive_reconnection(max_wait_time=10)
                
                assert result is True
                
    def test_wait_for_drive_reconnection_timeout(self):
        """Test drive reconnection timeout."""
        with patch.object(self.tool, '_is_drive_accessible', return_value=False):
            with patch('time.sleep'):  # Speed up test
                result = self.tool._wait_for_drive_reconnection(max_wait_time=1)
                
                assert result is False
                
    def test_wait_for_drive_reconnection_immediate_success(self):
        """Test immediate drive reconnection success."""
        with patch.object(self.tool, '_is_drive_accessible', return_value=True):
            result = self.tool._wait_for_drive_reconnection(max_wait_time=10)
            
            assert result is True
            
    def test_copy_file_with_retry_drive_issue(self):
        """Test file copy with retry due to drive issues."""
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        
        file_info = {
            'hash': 'ed7002b439e9ac845f22357d822bac1444730fbdb6016d3ec9432297b9ec9f73',  # sha256 of "content"
            'size': 7
        }
        
        # Test that drive accessibility checking works during retry
        call_count = 0
        
        def mock_drive_accessible():
            nonlocal call_count
            call_count += 1
            return call_count > 1  # First call returns False, subsequent return True
        
        # Actually perform the copy but test the retry logic
        with patch.object(self.tool, '_is_drive_accessible', side_effect=mock_drive_accessible):
            with patch.object(self.tool, '_wait_for_drive_reconnection', return_value=True):
                with patch('time.sleep'):  # Speed up test
                    result = self.tool._copy_file_with_retry(source_file, dest_file, file_info)
                    
                    # Should succeed despite initial drive accessibility issue
                    assert result is True
                    assert dest_file.exists()
                    assert dest_file.read_text() == "content"
                        
    def test_copy_file_with_retry_max_retries_exceeded(self):
        """Test file copy with retry when max retries exceeded."""
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        
        file_info = {
            'hash': 'ed7002b439e9ac845f22357d822bac1444730fbdb6016d3ec9432297b9ec9f73',
            'size': 7
        }
        
        # Mock persistent copy failure
        with patch('shutil.copy2', side_effect=OSError("Persistent error")):
            with patch.object(self.tool, '_is_drive_accessible', return_value=True):
                with patch('time.sleep'):  # Speed up test
                    result = self.tool._copy_file_with_retry(source_file, dest_file, file_info)
                    
                    assert result is False
                    
    def test_copy_file_with_retry_hash_mismatch(self):
        """Test file copy with retry due to hash mismatch."""
        source_file = self.source_dir / "test.txt"
        dest_file = self.dest_dir / "test.txt"
        source_file.write_text("content")
        
        file_info = {
            'hash': 'wrong_hash',
            'size': 7
        }
        
        # Mock successful copy but wrong hash
        with patch('shutil.copy2'):
            with patch('time.sleep'):  # Speed up test
                result = self.tool._copy_file_with_retry(source_file, dest_file, file_info)
                
                assert result is False


class TestProgressStateManagement:
    """Test cases for progress state save/load functionality."""
    
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
        
    def test_save_progress_state_success(self):
        """Test successful progress state saving."""
        manifest = {'test': 'data'}
        completed_files = ['file1.txt', 'file2.txt']
        failed_files = ['file3.txt']
        
        result = self.tool._save_progress_state(manifest, completed_files, failed_files)
        
        assert result is True
        
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        assert progress_file.exists()
        
        with open(progress_file) as f:
            progress_data = json.load(f)
            
        assert progress_data['operation'] == 'copy'
        assert progress_data['completed_files'] == completed_files
        assert progress_data['failed_files'] == failed_files
        assert progress_data['manifest_snapshot'] == manifest
        
    def test_save_progress_state_failure(self):
        """Test progress state saving failure."""
        manifest = {'test': 'data'}
        completed_files = ['file1.txt']
        failed_files = []
        
        with patch('builtins.open', side_effect=OSError("Permission denied")):
            result = self.tool._save_progress_state(manifest, completed_files, failed_files)
            
            assert result is False
            
    def test_load_progress_state_success(self):
        """Test successful progress state loading."""
        progress_data = {
            'timestamp': '2024-01-01T12:00:00',
            'operation': 'copy',
            'completed_files': ['file1.txt'],
            'failed_files': [],
            'manifest_snapshot': {'test': 'data'}
        }
        
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
            
        result = self.tool._load_progress_state()
        
        assert result == progress_data
        
    def test_load_progress_state_no_file(self):
        """Test loading progress state when file doesn't exist."""
        result = self.tool._load_progress_state()
        
        assert result is None
        
    def test_load_progress_state_corrupted(self):
        """Test loading corrupted progress state file."""
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        progress_file.write_text("invalid json")
        
        result = self.tool._load_progress_state()
        
        assert result is None
        
    def test_clear_progress_state(self):
        """Test clearing progress state file."""
        # Create progress file
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        progress_file.write_text("test data")
        
        assert progress_file.exists()
        
        self.tool._clear_progress_state()
        
        assert not progress_file.exists()
        
    def test_clear_progress_state_no_file(self):
        """Test clearing progress state when file doesn't exist."""
        # Should not raise any errors
        self.tool._clear_progress_state()


class TestFileScanningAndExclusion:
    """Test cases for file scanning and exclusion logic."""
    
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
        
    def test_scan_directory_with_exclusions(self):
        """Test directory scanning with file exclusions."""
        # Create various files
        (self.source_dir / "regular.txt").write_text("content")
        (self.source_dir / ".DS_Store").write_text("system")
        (self.source_dir / "temp.tmp").write_text("temp")
        (self.source_dir / "script.pyc").write_text("compiled")
        (self.source_dir / "~$document.docx").write_text("office temp")
        
        # Create subdirectory
        subdir = self.source_dir / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested content")
        (subdir / "__pycache__").mkdir()  # Should be excluded
        
        files_info = self.tool._scan_directory(self.source_dir)
        
        # Should only include regular files, not excluded ones
        relative_paths = [f['relative_path'] for f in files_info]
        
        assert "regular.txt" in relative_paths
        assert str(Path("subdir") / "nested.txt") in relative_paths
        assert ".DS_Store" not in relative_paths
        assert "temp.tmp" not in relative_paths
        assert "script.pyc" not in relative_paths
        assert "~$document.docx" not in relative_paths
        
    def test_scan_directory_file_error(self):
        """Test directory scanning with file access errors."""
        # Create a file
        test_file = self.source_dir / "test.txt"
        test_file.write_text("content")
        
        # Mock file stat to raise an error
        with patch.object(Path, 'stat', side_effect=OSError("Permission denied")):
            files_info = self.tool._scan_directory(self.source_dir)
            
            # Should continue despite error and return empty list
            assert len(files_info) == 0
            
    def test_scan_directory_hash_calculation_error(self):
        """Test directory scanning with hash calculation errors."""
        # Create a file
        test_file = self.source_dir / "test.txt"
        test_file.write_text("content")
        
        # Mock hash calculation to raise an error
        with patch.object(self.tool, '_calculate_hash', side_effect=RuntimeError("Hash error")):
            files_info = self.tool._scan_directory(self.source_dir)
            
            # Should continue despite error and return empty list
            assert len(files_info) == 0
            
    @patch('platform.system')
    def test_exclusion_patterns_comprehensive(self, mock_platform):
        """Test comprehensive exclusion pattern matching."""
        mock_platform.return_value = 'Darwin'  # Enable macOS patterns
        tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
        test_cases = [
            # Exact matches
            (".DS_Store", True),
            ("Thumbs.db", True),
            (".git", True),
            ("__pycache__", True),
            
            # Prefix patterns
            ("~$document.docx", True),
            ("._metadata", True),
            (".PKInstallSandboxManager-SystemSoftware", True),
            
            # Suffix patterns
            ("script.pyc", True),
            ("module.pyo", True),
            ("file.tmp", True),
            ("data.temp", True),
            
            # Should not be excluded
            ("regular.txt", False),
            ("document.pdf", False),
            ("image.jpg", False),
            ("DSStore.txt", False),  # Contains .DS_Store but not exact match
        ]
        
        for filename, should_exclude in test_cases:
            file_path = Path(filename)
            result = tool._should_exclude(file_path)
            assert result == should_exclude, f"File {filename} exclusion test failed"


import json

if __name__ == "__main__":
    pytest.main([__file__])
