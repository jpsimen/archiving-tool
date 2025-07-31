"""Simplified unit tests using pytest fixtures."""

import hashlib
import json
import time
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from archiving_tool.core import ArchivingTool
from tests.conftest import TestUtils, SAMPLE_DIRECTORY_STRUCTURE


class TestArchivingToolWithFixtures:
    """Test ArchivingTool using pytest fixtures."""
    
    def test_init_basic_functionality(self, archiving_tool, sample_files):
        """Test basic initialization functionality."""
        result = archiving_tool.init()
        
        assert result is True
        assert archiving_tool.manifest_file.exists()
        
        # Load and verify manifest
        with open(archiving_tool.manifest_file) as f:
            manifest = json.load(f)
            
        # Should include 4 non-excluded files
        assert manifest['total_files'] == 4
        assert 'simple.txt' in manifest['files']
        assert 'empty.txt' in manifest['files']
        assert str(Path('subdir') / 'nested.txt') in manifest['files']
        assert str(Path('subdir') / 'binary.bin') in manifest['files']
        
        # Should exclude system files
        assert '.DS_Store' not in manifest['files']
        assert 'temp.tmp' not in manifest['files']
        
    def test_copy_workflow(self, archiving_tool, sample_files):
        """Test the complete copy workflow."""
        # Initialize
        assert archiving_tool.init() is True
        
        # Copy files
        assert archiving_tool.copy() is True
        
        # Verify files were copied
        dest_dir = archiving_tool.destination_dir
        assert (dest_dir / "simple.txt").read_text() == "simple content"
        assert (dest_dir / "empty.txt").exists()
        assert (dest_dir / "subdir" / "nested.txt").read_text() == "nested content"
        assert (dest_dir / "subdir" / "binary.bin").read_bytes() == b"\x00\x01\x02\x03\x04"
        
        # Excluded files should not be copied
        assert not (dest_dir / ".DS_Store").exists()
        assert not (dest_dir / "temp.tmp").exists()
        
    def test_update_workflow(self, archiving_tool, temp_workspace):
        """Test the update workflow."""
        source_dir = temp_workspace['source_dir']
        
        # Create initial files
        TestUtils.create_test_file(source_dir / "file1.txt", "initial content")
        TestUtils.create_test_file(source_dir / "file2.txt", "initial content 2")
        
        # Initialize and copy
        assert archiving_tool.init() is True
        assert archiving_tool.copy() is True
        
        # Add new file
        TestUtils.create_test_file(source_dir / "file3.txt", "new content")
        
        # Modify existing file
        time.sleep(0.1)  # Ensure different mtime
        TestUtils.create_test_file(source_dir / "file1.txt", "modified content")
        
        # Delete a file
        (source_dir / "file2.txt").unlink()
        
        # Update
        assert archiving_tool.update() is True
        
        # Verify changes
        dest_dir = archiving_tool.destination_dir
        assert (dest_dir / "file1.txt").read_text() == "modified content"
        assert (dest_dir / "file3.txt").read_text() == "new content"
        # file2.txt should still exist in destination (update doesn't delete)
        assert (dest_dir / "file2.txt").exists()
        
        # Verify manifest
        with open(archiving_tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert 'file1.txt' in manifest['files']
        assert 'file3.txt' in manifest['files']
        assert 'file2.txt' not in manifest['files']  # Removed from manifest
        
    def test_verify_workflow(self, archiving_tool, sample_files):
        """Test the verify workflow."""
        # Initialize and copy
        assert archiving_tool.init() is True
        assert archiving_tool.copy() is True
        
        # Verify should succeed
        assert archiving_tool.verify() is True
        
        # Corrupt a file
        dest_file = archiving_tool.destination_dir / "simple.txt"
        dest_file.write_text("corrupted content")
        
        # Verify should fail
        assert archiving_tool.verify() is False
        
    def test_status_display(self, archiving_tool, sample_files):
        """Test status display functionality."""
        # Should fail with no manifest
        assert archiving_tool.status() is False
        
        # Initialize
        assert archiving_tool.init() is True
        
        # Status should succeed
        assert archiving_tool.status() is True
        
    def test_dry_run_functionality(self, archiving_tool, sample_files):
        """Test dry run functionality."""
        # Initialize
        assert archiving_tool.init() is True
        
        # Dry run copy
        assert archiving_tool.copy(dry_run=True) is True
        
        # Files should not be copied
        dest_dir = archiving_tool.destination_dir
        assert not (dest_dir / "simple.txt").exists()
        assert not (dest_dir / "empty.txt").exists()
        
        # Dry run update
        source_dir = archiving_tool.source_dir
        TestUtils.create_test_file(source_dir / "new.txt", "new")
        assert archiving_tool.update(dry_run=True) is True
        
        # Manifest should not be updated
        with open(archiving_tool.manifest_file) as f:
            manifest = json.load(f)
        assert 'new.txt' not in manifest['files']
        
    def test_complex_directory_structure(self, temp_workspace, archiving_tool):
        """Test with complex directory structure."""
        source_dir = temp_workspace['source_dir']
        
        # Create complex structure
        created_paths = TestUtils.create_directory_structure(source_dir, SAMPLE_DIRECTORY_STRUCTURE)
        
        # Initialize
        assert archiving_tool.init() is True
        
        # Copy
        assert archiving_tool.copy() is True
        
        # Verify structure was copied correctly
        dest_dir = archiving_tool.destination_dir
        
        # Check some key files
        assert (dest_dir / "file1.txt").read_text() == "Content of file 1"
        assert (dest_dir / "subdir1" / "nested1.txt").read_text() == "Nested content 1"
        assert (dest_dir / "subdir1" / "deep" / "deep_file.txt").read_text() == "Deep nested content"
        assert (dest_dir / "empty.txt").read_text() == ""
        
        # Check excluded files  
        assert not (dest_dir / ".DS_Store").exists()
        assert not (dest_dir / "temp.tmp").exists()
        
        # Verify
        assert archiving_tool.verify() is True
        
    @pytest.mark.parametrize("chunk_size", [1024, 8192, 65536])
    def test_different_chunk_sizes(self, temp_workspace, chunk_size):
        """Test hash calculation with different chunk sizes."""
        source_dir = temp_workspace['source_dir']
        dest_dir = temp_workspace['dest_dir']
        
        tool = ArchivingTool(str(source_dir), str(dest_dir))
        tool.chunk_size = chunk_size
        
        # Create test file
        content = "test content " * 1000  # ~13KB
        test_file = TestUtils.create_test_file(source_dir / "test.txt", content)
        
        # Calculate hash
        result_hash = tool._calculate_hash(test_file)
        expected_hash = hashlib.sha256(content.encode()).hexdigest()
        
        assert result_hash == expected_hash
        
    @pytest.mark.parametrize("file_size", [0, 1, 1023, 1024, 1025, 65535, 65536, 65537])
    def test_edge_case_file_sizes(self, temp_workspace, file_size):
        """Test handling of edge case file sizes."""
        source_dir = temp_workspace['source_dir']
        dest_dir = temp_workspace['dest_dir']
        
        tool = ArchivingTool(str(source_dir), str(dest_dir))
        
        # Create file of specific size
        if file_size == 0:
            test_file = source_dir / "test.txt"
            test_file.touch()
        else:
            content = "x" * file_size
            test_file = TestUtils.create_test_file(source_dir / "test.txt", content)
        
        # Test workflow
        assert tool.init() is True
        assert tool.copy() is True
        assert tool.verify() is True
        
        # Verify file size in manifest
        with open(tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['files']['test.txt']['size'] == file_size
        
    def test_error_handling_with_fixtures(self, archiving_tool, sample_files):
        """Test error handling scenarios."""
        # Test with corrupted manifest
        archiving_tool.init()
        archiving_tool.manifest_file.write_text("invalid json")
        
        assert archiving_tool._load_manifest() is None
        assert archiving_tool.copy() is False
        assert archiving_tool.update() is False
        assert archiving_tool.verify() is False
        
    def test_resume_functionality(self, archiving_tool, sample_files):
        """Test resume functionality."""
        # Create progress state
        progress_data = {
            'timestamp': '2024-01-01T12:00:00',
            'operation': 'copy',
            'completed_files': ['simple.txt'],
            'failed_files': [],
            'manifest_snapshot': {}
        }
        
        progress_file = archiving_tool.destination_dir / ".archiving_tool_progress.json"
        with open(progress_file, 'w') as f:
            json.dump(progress_data, f)
            
        # Mock copy to verify resume calls it
        with patch.object(archiving_tool, 'copy') as mock_copy:
            mock_copy.return_value = True
            
            result = archiving_tool.resume()
            
            assert result is True
            mock_copy.assert_called_once_with(dry_run=False)
            
    @pytest.mark.slow
    def test_performance_with_many_files(self, temp_workspace):
        """Test performance with many files."""
        source_dir = temp_workspace['source_dir']
        dest_dir = temp_workspace['dest_dir']
        
        tool = ArchivingTool(str(source_dir), str(dest_dir))
        
        # Create many small files
        num_files = 200
        for i in range(num_files):
            TestUtils.create_test_file(source_dir / f"file_{i:04d}.txt", f"content_{i}")
            
        # Test performance
        start_time = time.time()
        assert tool.init() is True
        init_time = time.time() - start_time
        
        start_time = time.time()
        assert tool.copy() is True
        copy_time = time.time() - start_time
        
        start_time = time.time()
        assert tool.verify() is True
        verify_time = time.time() - start_time
        
        # Performance should be reasonable
        assert init_time < 30
        assert copy_time < 30
        assert verify_time < 30
        
        # Verify all files were processed
        with open(tool.manifest_file) as f:
            manifest = json.load(f)
            
        assert manifest['total_files'] == num_files


@pytest.mark.integration
class TestIntegrationWorkflows:
    """Integration tests for complete workflows."""
    
    def test_complete_archiving_workflow(self, temp_workspace):
        """Test a complete archiving workflow from start to finish."""
        source_dir = temp_workspace['source_dir']
        dest_dir = temp_workspace['dest_dir']
        
        tool = ArchivingTool(str(source_dir), str(dest_dir))
        
        # Phase 1: Initial setup
        initial_files = {
            "documents": {
                "report.txt": "Annual report content",
                "notes.txt": "Meeting notes",
                "archive": {
                    "old_report.txt": "Last year's report"
                }
            },
            "media": {
                "photo.jpg": "fake jpg content",
                "video.mp4": "fake video content"
            },
            "config.ini": "configuration data",
            ".DS_Store": "hidden file content"  # This will be excluded
        }
        
        TestUtils.create_directory_structure(source_dir, initial_files)
        
        # Initialize archive
        assert tool.init() is True
        
        # Phase 2: Copy files
        assert tool.copy() is True
        
        # Verify initial copy
        assert tool.verify() is True
        
        # Phase 3: Make changes
        # Add new files
        TestUtils.create_test_file(source_dir / "new_file.txt", "new content")
        TestUtils.create_test_file(source_dir / "documents" / "updated.txt", "updated content")
        
        # Modify existing file
        time.sleep(0.1)
        TestUtils.create_test_file(source_dir / "config.ini", "updated configuration")
        
        # Delete a file
        (source_dir / "media" / "photo.jpg").unlink()
        
        # Phase 4: Update archive
        assert tool.update() is True
        
        # Phase 5: Final verification
        assert tool.verify() is True
        
        # Phase 6: Status check
        assert tool.status() is True
        
        # Verify final state
        assert (dest_dir / "new_file.txt").read_text() == "new content"
        assert (dest_dir / "documents" / "updated.txt").read_text() == "updated content"
        assert (dest_dir / "config.ini").read_text() == "updated configuration"
        
        # Original files should still exist
        assert (dest_dir / "documents" / "report.txt").read_text() == "Annual report content"
        assert (dest_dir / "documents" / "archive" / "old_report.txt").read_text() == "Last year's report"
        
        # Deleted file should still exist in destination
        assert (dest_dir / "media" / "photo.jpg").exists()
        
        # Hidden file should be excluded
        assert not (dest_dir / ".DS_Store").exists()


if __name__ == "__main__":
    pytest.main([__file__])
