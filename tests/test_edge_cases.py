"""Tests for edge cases in the archiving tool."""

import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from archiving_tool.core import ArchivingTool


class TestEdgeCases:
    """Test suite for edge cases."""

    def setup_method(self):
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.source_dir = self.test_dir / "source"
        self.dest_dir = self.test_dir / "dest"
        
        # Create test directories
        self.source_dir.mkdir()
        self.dest_dir.mkdir()
        
        # Initialize archiving tool
        self.tool = ArchivingTool(str(self.source_dir), str(self.dest_dir))
        
    def teardown_method(self):
        """Clean up test environment."""
        shutil.rmtree(self.test_dir)

    def test_empty_source_directory(self):
        """Test behavior with empty source directory."""
        # Source directory is already empty from setup
        self.tool.init()
        result = self.tool.copy()
        assert result is True
        
    def test_special_characters_in_filenames(self):
        """Test handling of special characters in filenames."""
        special_chars = [
            "file with spaces.txt",
            "file_with_!@#$%^&().txt",
            "file_with_unicode_日本語.txt",
            "file_with_emoji_🐍.txt"
        ]
        
        # Create test files with special characters
        for filename in special_chars:
            test_file = self.source_dir / filename
            test_file.write_text("Test content")
            
        self.tool.init()
        result = self.tool.copy()
        assert result is True
        
        # Verify files were copied correctly
        for filename in special_chars:
            assert (self.dest_dir / filename).exists()
            assert (self.dest_dir / filename).read_text() == "Test content"
            
    def test_very_long_paths(self):
        """Test handling of very long paths."""
        # Create deeply nested directory structure
        deep_path = self.source_dir
        for i in range(15):  # Create reasonable but deep nesting
            deep_path = deep_path / f"subfolder_{i}"
            deep_path.mkdir()
            
        test_file = deep_path / "test.txt"
        test_file.write_text("Test content")
        
        self.tool.init()
        result = self.tool.copy()
        assert result is True
        
        # Verify file was copied with full path structure
        dest_path = self.dest_dir
        for i in range(15):
            dest_path = dest_path / f"subfolder_{i}"
        assert (dest_path / "test.txt").exists()
        assert (dest_path / "test.txt").read_text() == "Test content"
        
    def test_zero_byte_files(self):
        """Test handling of zero-byte files."""
        empty_file = self.source_dir / "empty.txt"
        empty_file.touch()  # Creates a zero-byte file
        
        self.tool.init()
        result = self.tool.copy()
        assert result is True
        
        dest_file = self.dest_dir / "empty.txt"
        assert dest_file.exists()
        assert dest_file.stat().st_size == 0
        
    def test_hidden_files_and_directories(self):
        """Test handling of hidden files and directories."""
        # Create hidden directory
        hidden_dir = self.source_dir / ".hidden_dir"
        hidden_dir.mkdir()
        
        # Create hidden file in root
        hidden_file1 = self.source_dir / ".hidden_file"
        hidden_file1.write_text("Hidden content")
        
        # Create hidden file in hidden directory
        hidden_file2 = hidden_dir / ".nested_hidden_file"
        hidden_file2.write_text("Nested hidden content")
        
        self.tool.init()
        result = self.tool.copy()
        assert result is True
        
        # Verify hidden files and directories were copied
        assert (self.dest_dir / ".hidden_dir").exists()
        assert (self.dest_dir / ".hidden_file").exists()
        assert (self.dest_dir / ".hidden_dir" / ".nested_hidden_file").exists()
        
        # Verify content
        assert (self.dest_dir / ".hidden_file").read_text() == "Hidden content"
        assert (self.dest_dir / ".hidden_dir" / ".nested_hidden_file").read_text() == "Nested hidden content"

    def test_symlinks(self):
        """Test handling of symbolic links."""
        # Create a real file
        real_file = self.source_dir / "real_file.txt"
        real_file.write_text("Real content")
        
        # Create a symlink to the real file
        symlink = self.source_dir / "symlink.txt"
        os.symlink(str(real_file), str(symlink))
        
        self.tool.init()
        result = self.tool.copy()
        assert result is True
        
        # Verify both real file and symlink were copied
        assert (self.dest_dir / "real_file.txt").exists()
        assert (self.dest_dir / "symlink.txt").exists()
        assert (self.dest_dir / "real_file.txt").read_text() == "Real content"
        assert (self.dest_dir / "symlink.txt").read_text() == "Real content"
