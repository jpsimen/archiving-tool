"""Configuration for pytest tests."""

import pytest
import tempfile
import shutil
from pathlib import Path


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for tests."""
    temp_dir = tempfile.mkdtemp()
    workspace = {
        'temp_dir': Path(temp_dir),
        'source_dir': Path(temp_dir) / "source",
        'dest_dir': Path(temp_dir) / "dest",
    }
    
    workspace['source_dir'].mkdir()
    workspace['dest_dir'].mkdir()
    
    yield workspace
    
    # Cleanup
    shutil.rmtree(temp_dir)


@pytest.fixture
def archiving_tool(temp_workspace):
    """Create an ArchivingTool instance with temporary directories."""
    from archiving_tool.core import ArchivingTool
    
    return ArchivingTool(
        str(temp_workspace['source_dir']),
        str(temp_workspace['dest_dir'])
    )


@pytest.fixture
def sample_files(temp_workspace):
    """Create sample files for testing."""
    source_dir = temp_workspace['source_dir']
    
    # Create various test files
    (source_dir / "simple.txt").write_text("simple content")
    (source_dir / "empty.txt").touch()
    
    # Create subdirectory with files
    subdir = source_dir / "subdir"
    subdir.mkdir()
    (subdir / "nested.txt").write_text("nested content")
    (subdir / "binary.bin").write_bytes(b"\x00\x01\x02\x03\x04")
    
    # Create files that should be excluded
    (source_dir / ".DS_Store").write_text("system file")
    (source_dir / "temp.tmp").write_text("temporary file")
    
    return {
        'simple': source_dir / "simple.txt",
        'empty': source_dir / "empty.txt",
        'nested': subdir / "nested.txt",
        'binary': subdir / "binary.bin",
        'excluded_ds': source_dir / ".DS_Store",
        'excluded_tmp': source_dir / "temp.tmp",
    }


# Markers for different test categories
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "macos: marks tests as macOS-specific"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )


# Test utilities
class TestUtils:
    """Utility functions for tests."""
    
    @staticmethod
    def create_test_file(path: Path, content: str = "test content") -> Path:
        """Create a test file with specified content."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path
    
    @staticmethod
    def create_binary_file(path: Path, size: int = 1024) -> Path:
        """Create a binary test file of specified size."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = bytes(i % 256 for i in range(size))
        path.write_bytes(data)
        return path
    
    @staticmethod
    def verify_file_copied(source: Path, dest: Path) -> bool:
        """Verify that a file was copied correctly."""
        if not dest.exists():
            return False
        
        if source.is_file() and dest.is_file():
            return source.read_bytes() == dest.read_bytes()
        
        return False
    
    @staticmethod
    def create_directory_structure(base_dir: Path, structure: dict) -> dict:
        """Create a directory structure from a dictionary specification.
        
        Args:
            base_dir: Base directory to create structure in
            structure: Dict where keys are paths and values are either:
                - str: file content
                - dict: subdirectory structure
                - None: empty directory
                
        Returns:
            Dict mapping names to created paths
        """
        created_paths = {}
        
        for name, content in structure.items():
            path = base_dir / name
            
            if isinstance(content, dict):
                # Subdirectory
                path.mkdir(parents=True, exist_ok=True)
                created_paths[name] = path
                # Recursively create subdirectory contents
                sub_paths = TestUtils.create_directory_structure(path, content)
                created_paths.update({f"{name}/{k}": v for k, v in sub_paths.items()})
            elif isinstance(content, str):
                # File with content
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
                created_paths[name] = path
            elif content is None:
                # Empty directory
                path.mkdir(parents=True, exist_ok=True)
                created_paths[name] = path
            else:
                raise ValueError(f"Unsupported content type for {name}: {type(content)}")
                
        return created_paths


# Common test data
SAMPLE_DIRECTORY_STRUCTURE = {
    "file1.txt": "Content of file 1",
    "file2.txt": "Content of file 2",
    "subdir1": {
        "nested1.txt": "Nested content 1",
        "nested2.txt": "Nested content 2",
        "deep": {
            "deep_file.txt": "Deep nested content"
        }
    },
    "subdir2": {
        "binary.bin": "Binary content",
        "empty_subdir": None
    },
    "empty.txt": "",
    ".DS_Store": "Should be excluded",  # This will be excluded
    "temp.tmp": "Temporary file",       # This will be excluded
}

# Test constants
TEST_CHUNK_SIZES = [1024, 8192, 65536]  # Different chunk sizes to test
TEST_FILE_SIZES = [0, 1, 1023, 1024, 1025, 65535, 65536, 65537]  # Edge case file sizes
