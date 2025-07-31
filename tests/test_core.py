"""Comprehensive unit tests for the ArchivingTool class."""

import hashlib
import json
import os
import platform
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

import pytest

from archiving_tool.core import ArchivingTool


class TestArchivingToolInit:
    """Test cases for ArchivingTool initialization."""
    
    def test_init_basic(self, tmp_path):
        """Test basic initialization with source and destination directories."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        
        tool = ArchivingTool(str(source_dir), str(dest_dir))
        
        assert tool.source_dir == source_dir.resolve()
        assert tool.destination_dir == dest_dir.resolve()
        assert tool.manifest_file == dest_dir.resolve() / ".archiving_manifest.json"
        assert tool.max_retries == 3
        assert tool.retry_delay == 2.0
        
    def test_init_custom_manifest(self, tmp_path):
        """Test initialization with custom manifest file."""
        source_dir = tmp_path / "source"
        dest_dir = tmp_path / "dest"
        manifest_file = tmp_path / "custom_manifest.json"
        
        tool = ArchivingTool(str(source_dir), str(dest_dir), str(manifest_file))
        
        assert tool.manifest_file == manifest_file.resolve()
        
    def test_init_path_resolution(self, tmp_path):
        """Test that paths are properly resolved."""
        # Use relative paths
        os.chdir(tmp_path)
        source_dir = "source"
        dest_dir = "dest"
        
        tool = ArchivingTool(source_dir, dest_dir)
        
        # Paths should be resolved to absolute
        assert tool.source_dir.is_absolute()
        assert tool.destination_dir.is_absolute()
        assert tool.source_dir.name == "source"
        assert tool.destination_dir.name == "dest"
        
    def test_init_exclusion_patterns_default(self, tmp_path):
        """Test default exclusion patterns."""
        tool = ArchivingTool(str(tmp_path / "source"), str(tmp_path / "dest"))
        
        expected_patterns = {
            '.DS_Store', 'Thumbs.db', '.tmp', '.temp', '~$*', '*.tmp', '*.temp',
            '.git', '.svn', '.hg', '__pycache__', '*.pyc', '*.pyo'
        }
        
        assert expected_patterns.issubset(tool.exclusion_patterns)
        
    @patch('platform.system')
    def test_init_macos_exclusions(self, mock_platform, tmp_path):
        """Test macOS-specific exclusion patterns."""
        mock_platform.return_value = 'Darwin'
        
        tool = ArchivingTool(str(tmp_path / "source"), str(tmp_path / "dest"))
        
        macos_patterns = {
            '.Spotlight-V100', '.Trashes', '.fseventsd', '.TemporaryItems',
            '.DocumentRevisions-V100', '.PKInstallSandboxManager*',
            '._*', '.localized', '.VolumeIcon.icns'
        }
        
        assert macos_patterns.issubset(tool.exclusion_patterns)
        assert tool.is_macos is True
        assert tool.chunk_size == 1024 * 1024  # 1MB for macOS
        
    @patch('platform.system')
    def test_init_non_macos(self, mock_platform, tmp_path):
        """Test initialization on non-macOS systems."""
        mock_platform.return_value = 'Linux'
        
        tool = ArchivingTool(str(tmp_path / "source"), str(tmp_path / "dest"))
        
        assert tool.is_macos is False
        assert tool.chunk_size == 8192  # Default chunk size


class TestArchivingToolInit:
    """Test cases for the init method."""
    
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
        
    def create_test_files(self):
        """Create test files in source directory."""
        # Create some test files
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        
        # Create subdirectory with file
        subdir = self.source_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")
        
        # Create file that should be excluded
        (self.source_dir / ".DS_Store").write_text("system file")
        
    def test_init_success(self):
        """Test successful initialization."""
        self.create_test_files()
        
        result = self.tool.init()
        
        assert result is True
        assert self.tool.manifest_file.exists()
        
        # Verify manifest content
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['source_dir'] == str(self.source_dir)
        assert manifest['destination_dir'] == str(self.dest_dir)
        assert manifest['total_files'] == 3  # Excludes .DS_Store
        assert 'created' in manifest
        assert 'files' in manifest
        
        # Check that excluded files are not in manifest
        assert '.DS_Store' not in manifest['files']
        
    def test_init_force_overwrite(self):
        """Test force overwrite of existing manifest."""
        self.create_test_files()
        
        # Create initial manifest
        self.tool.init()
        original_time = self.tool.manifest_file.stat().st_mtime
        
        # Wait a bit to ensure different timestamp
        time.sleep(0.1)
        
        # Force overwrite
        result = self.tool.init(force=True)
        
        assert result is True
        new_time = self.tool.manifest_file.stat().st_mtime
        assert new_time > original_time
        
    def test_init_existing_manifest_no_force(self):
        """Test that existing manifest is not overwritten without force."""
        self.create_test_files()
        
        # Create initial manifest
        self.tool.init()
        original_content = self.tool.manifest_file.read_text()
        
        # Try to init again without force
        result = self.tool.init(force=False)
        
        assert result is False
        assert self.tool.manifest_file.read_text() == original_content
        
    def test_init_nonexistent_source(self):
        """Test initialization with nonexistent source directory."""
        self.source_dir.rmdir()
        
        result = self.tool.init()
        
        assert result is False
        assert not self.tool.manifest_file.exists()
        
    def test_init_empty_directory(self):
        """Test initialization with empty source directory."""
        result = self.tool.init()
        
        assert result is True
        
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == 0
        assert manifest['total_size'] == 0
        assert manifest['files'] == {}
        
    def test_init_file_hash_calculation(self):
        """Test that file hashes are calculated correctly."""
        test_content = "test content for hashing"
        test_file = self.source_dir / "test.txt"
        test_file.write_text(test_content)
        
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()
        
        self.tool.init()
        
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        file_info = manifest['files']['test.txt']
        assert file_info['hash'] == expected_hash
        assert file_info['size'] == len(test_content.encode())
        
    @patch('archiving_tool.core.ArchivingTool._scan_directory')
    def test_init_scan_directory_error(self, mock_scan):
        """Test handling of scan directory errors."""
        mock_scan.side_effect = OSError("Permission denied")
        
        self.create_test_files()
        
        # Should handle the error gracefully
        with pytest.raises(OSError):
            self.tool.init()


class TestArchivingToolCopy:
    """Test cases for the copy method."""
    
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
        
    def create_test_files_and_manifest(self):
        """Create test files and initialize manifest."""
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        
        subdir = self.source_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")
        
        self.tool.init()
        
    def test_copy_no_manifest(self):
        """Test copy with no existing manifest."""
        result = self.tool.copy()
        
        assert result is False
        
    def test_copy_success(self):
        """Test successful copy operation."""
        self.create_test_files_and_manifest()
        
        result = self.tool.copy()
        
        assert result is True
        
        # Verify files were copied
        assert (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "file2.txt").exists()
        assert (self.dest_dir / "subdir" / "file3.txt").exists()
        
        # Verify content
        assert (self.dest_dir / "file1.txt").read_text() == "content1"
        assert (self.dest_dir / "file2.txt").read_text() == "content2"
        assert (self.dest_dir / "subdir" / "file3.txt").read_text() == "content3"
        
    def test_copy_dry_run(self):
        """Test copy dry run mode."""
        self.create_test_files_and_manifest()
        
        result = self.tool.copy(dry_run=True)
        
        assert result is True
        
        # Verify no files were actually copied
        assert not (self.dest_dir / "file1.txt").exists()
        assert not (self.dest_dir / "file2.txt").exists()
        
    def test_copy_already_exist_same_hash(self):
        """Test copy when files already exist with same hash."""
        self.create_test_files_and_manifest()
        
        # Copy files first time
        self.tool.copy()
        
        # Copy again - should verify existing files
        result = self.tool.copy()
        
        assert result is True
        
    def test_copy_already_exist_different_hash(self):
        """Test copy when files exist but with different hash."""
        self.create_test_files_and_manifest()
        
        # Create destination file with different content
        (self.dest_dir / "file1.txt").write_text("different content")
        
        result = self.tool.copy()
        
        assert result is True
        
        # Verify file was re-copied with correct content
        assert (self.dest_dir / "file1.txt").read_text() == "content1"
        
    def test_copy_missing_source_file(self):
        """Test copy when source file is missing."""
        self.create_test_files_and_manifest()
        
        # Remove source file after manifest creation
        (self.source_dir / "file1.txt").unlink()
        
        result = self.tool.copy()
        
        # Should still succeed, just skip missing file
        assert result is True
        assert not (self.dest_dir / "file1.txt").exists()
        assert (self.dest_dir / "file2.txt").exists()
        
    @patch('archiving_tool.core.ArchivingTool._is_drive_accessible')
    def test_copy_drive_not_accessible(self, mock_drive_check):
        """Test copy when drive is not accessible."""
        mock_drive_check.return_value = False
        
        self.create_test_files_and_manifest()
        
        result = self.tool.copy()
        
        assert result is False
        
    @patch('archiving_tool.core.ArchivingTool._copy_file_with_retry')
    def test_copy_file_copy_failure(self, mock_copy):
        """Test copy when file copy fails."""
        mock_copy.return_value = False
        
        self.create_test_files_and_manifest()
        
        result = self.tool.copy()
        
        assert result is False
        
    def test_copy_no_files_to_copy(self):
        """Test copy when all files are already up to date."""
        self.create_test_files_and_manifest()
        
        # Copy files first
        self.tool.copy()
        
        # Copy again with all files up to date
        result = self.tool.copy()
        
        assert result is True


class TestArchivingToolUpdate:
    """Test cases for the update method."""
    
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
        
    def test_update_no_manifest(self):
        """Test update with no existing manifest."""
        result = self.tool.update()
        
        assert result is False
        
    def test_update_no_changes(self):
        """Test update when no changes detected."""
        # Create initial files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        
        result = self.tool.update()
        
        assert result is True
        
    def test_update_new_files(self):
        """Test update with new files."""
        # Create initial files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        
        # Add new file
        (self.source_dir / "file2.txt").write_text("content2")
        
        result = self.tool.update()
        
        assert result is True
        
        # Verify manifest was updated
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert len(manifest['files']) == 2
        assert 'file2.txt' in manifest['files']
        assert 'last_updated' in manifest
        
    def test_update_modified_files(self):
        """Test update with modified files."""
        # Create initial files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        
        # Wait a bit to ensure different mtime
        time.sleep(0.1)
        
        # Modify file
        (self.source_dir / "file1.txt").write_text("modified content")
        
        result = self.tool.update()
        
        assert result is True
        
        # Verify manifest was updated with new hash
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        new_hash = hashlib.sha256("modified content".encode()).hexdigest()
        assert manifest['files']['file1.txt']['hash'] == new_hash
        
    def test_update_deleted_files(self):
        """Test update with deleted files."""
        # Create initial files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.init()
        
        # Delete file
        (self.source_dir / "file1.txt").unlink()
        
        result = self.tool.update()
        
        assert result is True
        
        # Verify manifest was updated
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert len(manifest['files']) == 1
        assert 'file1.txt' not in manifest['files']
        assert 'file2.txt' in manifest['files']
        
    def test_update_dry_run(self):
        """Test update dry run mode."""
        # Create initial files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        
        # Add new file
        (self.source_dir / "file2.txt").write_text("content2")
        
        result = self.tool.update(dry_run=True)
        
        assert result is True
        
        # Verify manifest was not actually updated
        with open(self.tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert len(manifest['files']) == 1  # Still only original file
        assert 'file2.txt' not in manifest['files']
        
    @patch('archiving_tool.core.ArchivingTool._copy_file_with_retry')
    def test_update_copy_failure(self, mock_copy):
        """Test update when file copy fails."""
        mock_copy.return_value = False
        
        # Create initial files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        
        # Add new file
        (self.source_dir / "file2.txt").write_text("content2")
        
        result = self.tool.update()
        
        assert result is False


class TestArchivingToolVerify:
    """Test cases for the verify method."""
    
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
        
    def test_verify_no_manifest(self):
        """Test verify with no manifest."""
        result = self.tool.verify()
        
        assert result is False
        
    def test_verify_success(self):
        """Test successful verification."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.init()
        self.tool.copy()
        
        result = self.tool.verify()
        
        assert result is True
        
    def test_verify_missing_file(self):
        """Test verification with missing destination file."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.init()
        self.tool.copy()
        
        # Remove one destination file
        (self.dest_dir / "file1.txt").unlink()
        
        result = self.tool.verify()
        
        assert result is False
        
    def test_verify_hash_mismatch(self):
        """Test verification with hash mismatch."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        self.tool.copy()
        
        # Modify destination file
        (self.dest_dir / "file1.txt").write_text("modified")
        
        result = self.tool.verify()
        
        assert result is False
        
    def test_verify_hash_calculation_error(self):
        """Test verification when hash calculation fails."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        self.tool.copy()
        
        # Make file unreadable (if possible on the platform)
        dest_file = self.dest_dir / "file1.txt"
        
        with patch('archiving_tool.core.ArchivingTool._calculate_hash') as mock_hash:
            mock_hash.side_effect = RuntimeError("Cannot read file")
            
            result = self.tool.verify()
            
            assert result is False


class TestArchivingToolResume:
    """Test cases for the resume method."""
    
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
        
    def test_resume_no_progress_state(self):
        """Test resume with no interrupted operations."""
        result = self.tool.resume()
        
        assert result is True
        
    def test_resume_with_progress_state(self):
        """Test resume with existing progress state."""
        # Create progress state file
        progress_data = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'copy',
            'completed_files': ['file1.txt'],
            'failed_files': [],
            'manifest_snapshot': {}
        }
        
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
            
        with patch.object(self.tool, 'copy') as mock_copy:
            mock_copy.return_value = True
            
            result = self.tool.resume()
            
            assert result is True
            mock_copy.assert_called_once_with(dry_run=False)
            
    def test_resume_unknown_operation(self):
        """Test resume with unknown operation type."""
        # Create progress state file with unknown operation
        progress_data = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'unknown',
            'completed_files': [],
            'failed_files': [],
            'manifest_snapshot': {}
        }
        
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
            
        result = self.tool.resume()
        
        assert result is False
        
    def test_resume_corrupted_progress_state(self):
        """Test resume with corrupted progress state file."""
        # Create corrupted progress state file
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        progress_file.write_text("invalid json")
        
        result = self.tool.resume()
        
        assert result is True  # Should handle gracefully


class TestArchivingToolStatus:
    """Test cases for the status method."""
    
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
        
    def test_status_no_manifest(self):
        """Test status with no manifest."""
        result = self.tool.status()
        
        assert result is False
        
    def test_status_success(self):
        """Test successful status display."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.init()
        self.tool.copy()
        
        result = self.tool.status()
        
        assert result is True
        
    def test_status_with_missing_files(self):
        """Test status when some destination files are missing."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.init()
        self.tool.copy()
        
        # Remove one destination file
        (self.dest_dir / "file1.txt").unlink()
        
        result = self.tool.status()
        
        assert result is True  # Status should complete even with missing files
        
    def test_status_with_last_updated(self):
        """Test status display with last_updated field."""
        # Create files and manifest
        (self.source_dir / "file1.txt").write_text("content1")
        self.tool.init()
        
        # Simulate update
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.update()
        
        result = self.tool.status()
        
        assert result is True


class TestArchivingToolHelperMethods:
    """Test cases for helper methods that are indirectly tested."""
    
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
        
    def test_calculate_hash(self):
        """Test hash calculation."""
        test_file = self.source_dir / "test.txt"
        test_content = "test content"
        test_file.write_text(test_content)
        
        result_hash = self.tool._calculate_hash(test_file)
        expected_hash = hashlib.sha256(test_content.encode()).hexdigest()
        
        assert result_hash == expected_hash
        
    def test_should_exclude(self):
        """Test file exclusion logic."""
        # Test exact match
        assert self.tool._should_exclude(Path(".DS_Store")) is True
        assert self.tool._should_exclude(Path("regular_file.txt")) is False
        
        # Test wildcard patterns
        assert self.tool._should_exclude(Path("temp.tmp")) is True
        assert self.tool._should_exclude(Path("~$document.docx")) is True
        assert self.tool._should_exclude(Path("script.pyc")) is True
        
    def test_get_relative_path(self):
        """Test relative path calculation."""
        test_file = self.source_dir / "subdir" / "file.txt"
        
        result = self.tool._get_relative_path(test_file)
        
        assert result == "subdir/file.txt" or result == "subdir\\file.txt"  # Handle OS differences
        
    def test_format_size(self):
        """Test size formatting."""
        assert self.tool._format_size(1024) == "1.0 KB"
        assert self.tool._format_size(1024 * 1024) == "1.0 MB"
        assert self.tool._format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert self.tool._format_size(500) == "500.0 B"


class TestArchivingToolErrorHandling:
    """Test cases for error handling scenarios."""
    
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
        
    def test_load_manifest_corrupted_json(self):
        """Test loading corrupted manifest file."""
        # Create corrupted manifest
        self.tool.manifest_file.write_text("invalid json")
        
        result = self.tool._load_manifest()
        
        assert result is None
        
    def test_save_manifest_permission_error(self):
        """Test saving manifest with permission error."""
        manifest = {'test': 'data'}
        
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.side_effect = PermissionError("Access denied")
            
            result = self.tool._save_manifest(manifest)
            
            assert result is False
            
    def test_hash_calculation_file_not_found(self):
        """Test hash calculation with missing file."""
        non_existent_file = self.source_dir / "missing.txt"
        
        with pytest.raises(RuntimeError):
            self.tool._calculate_hash(non_existent_file)
            
    def test_hash_calculation_permission_error(self):
        """Test hash calculation with permission error."""
        test_file = self.source_dir / "test.txt"
        test_file.write_text("content")
        
        with patch('builtins.open', mock_open()) as mock_file:
            mock_file.side_effect = PermissionError("Access denied")
            
            with pytest.raises(RuntimeError):
                self.tool._calculate_hash(test_file)


# Integration test class
class TestArchivingToolIntegration:
    """Integration tests for complete workflows."""
    
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
        
    def test_complete_workflow(self):
        """Test complete init -> copy -> update -> verify workflow."""
        # Step 1: Create initial files and init
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        
        assert self.tool.init() is True
        
        # Step 2: Copy files
        assert self.tool.copy() is True
        
        # Verify files were copied
        assert (self.dest_dir / "file1.txt").read_text() == "content1"
        assert (self.dest_dir / "file2.txt").read_text() == "content2"
        
        # Step 3: Add new file and update
        (self.source_dir / "file3.txt").write_text("content3")
        assert self.tool.update() is True
        
        # Verify new file was copied
        assert (self.dest_dir / "file3.txt").read_text() == "content3"
        
        # Step 4: Verify archive integrity
        assert self.tool.verify() is True
        
        # Step 5: Check status
        assert self.tool.status() is True
        
    def test_resume_workflow(self):
        """Test workflow with resume functionality."""
        # Create files and init
        (self.source_dir / "file1.txt").write_text("content1")
        (self.source_dir / "file2.txt").write_text("content2")
        self.tool.init()
        
        # Simulate partial copy with saved progress
        progress_data = {
            'timestamp': datetime.now().isoformat(),
            'operation': 'copy',
            'completed_files': ['file1.txt'],
            'failed_files': [],
            'manifest_snapshot': {}
        }
        
        progress_file = self.dest_dir / ".archiving_tool_progress.json"
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
            
        # Copy only one file manually to simulate partial completion
        (self.dest_dir / "file1.txt").write_text("content1")
        
        # Resume should complete the remaining files
        with patch.object(self.tool, 'copy') as mock_copy:
            mock_copy.return_value = True
            assert self.tool.resume() is True
            mock_copy.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
