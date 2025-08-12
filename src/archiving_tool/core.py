"""Core functionality for the archiving tool."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd
from tqdm import tqdm


class ArchivingTool:
    """Main archiving tool class."""
    
    def __init__(self, source_dir: str, destination_dir: str, manifest_file: Optional[str] = None):
        """Initialize the archiving tool.
        
        Args:
            source_dir: Path to source directory
            destination_dir: Path to destination directory  
            manifest_file: Optional path to manifest file (defaults to .archiving_manifest.json in dest)
        """
        self.source_dir = Path(source_dir).resolve()
        self.destination_dir = Path(destination_dir).resolve()
        
        # Detect if source is a network path for optimized handling
        self.is_network_source = self._is_network_path(self.source_dir)
        if self.is_network_source:
            print(f"Network source detected: {self.source_dir}")
            print("Enhanced network error handling and retry logic enabled")
            
            # Check if it's specifically an SMB mount for additional features
            try:
                if self._is_smb_mount(self.source_dir):
                    print("SMB/CIFS mount detected - automatic reconnection available")
            except:
                pass  # Don't fail initialization if SMB detection fails
        
        if manifest_file:
            self.manifest_file = Path(manifest_file).resolve()
        else:
            self.manifest_file = self.destination_dir / ".archiving_manifest.json"
            
        self.exclusion_patterns = {
            '.DS_Store', 'Thumbs.db', '.tmp', '.temp', '~$*', '*.tmp', '*.temp',
            '.git', '.svn', '.hg', '__pycache__', '*.pyc', '*.pyo'
        }
        
        # macOS-specific exclusions
        if platform.system() == 'Darwin':
            self.exclusion_patterns.update({
                '.Spotlight-V100', '.Trashes', '.fseventsd', '.TemporaryItems',
                '.DocumentRevisions-V100', '.PKInstallSandboxManager*',
                '._*',  # Resource forks and metadata files
                '.localized', '.VolumeIcon.icns'
            })
        
        # Retry configuration - enhanced for network reliability
        if self.is_network_source:
            self.max_retries = 8  # More retries for network sources
            self.retry_delay = 5.0  # Longer delays for network recovery
        else:
            self.max_retries = 5  # Standard for local sources
            self.retry_delay = 3.0  # Standard delay
        
        # Platform-specific optimizations
        self.is_macos = platform.system() == 'Darwin'
        self.chunk_size = 1024 * 1024 if self.is_macos else 8192  # 1MB chunks for macOS/APFS
        
        # Detect destination filesystem type
        self.dest_filesystem = self._detect_filesystem_type(self.destination_dir)
        if self.dest_filesystem:
            print(f"Detected destination filesystem: {self.dest_filesystem}")
        
    def _detect_filesystem_type(self, path: Path) -> Optional[str]:
        """Detect the filesystem type of the given path.
        
        Returns:
            Filesystem type (e.g., 'ext4', 'fat32', 'ntfs', 'apfs') or None if cannot be determined
        """
        try:
            if self.is_macos:
                result = subprocess.run(
                    ['diskutil', 'info', str(path)],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    output = result.stdout.lower()
                    if 'apfs' in output:
                        return 'apfs'
                    elif 'fat32' in output or 'msdos' in output:
                        return 'fat32'
                    elif 'ntfs' in output:
                        return 'ntfs'
                    elif 'hfs' in output:
                        return 'hfs'
            else:
                # Use findmnt on Linux
                result = subprocess.run(
                    ['findmnt', '-T', str(path), '-o', 'FSTYPE', '-n'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    fstype = result.stdout.strip().lower()
                    # Map common filesystem types
                    if fstype in ['vfat', 'msdos']:
                        return 'fat32'
                    return fstype
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None
        
    def _get_filesystem_max_filesize(self, fstype: Optional[str]) -> int:
        """Get the maximum file size supported by the filesystem.
        
        Args:
            fstype: Filesystem type string
            
        Returns:
            Maximum file size in bytes
        """
        if not fstype:
            # If we can't detect the filesystem, assume a large modern filesystem
            return float('inf')
            
        # Define maximum file sizes for different filesystems
        max_sizes = {
            'fat32': 4 * 1024 * 1024 * 1024 - 1,  # 4GB - 1 byte
            'vfat': 4 * 1024 * 1024 * 1024 - 1,   # 4GB - 1 byte
            'msdos': 4 * 1024 * 1024 * 1024 - 1,  # 4GB - 1 byte
            'ext4': float('inf'),    # Practically unlimited
            'ext3': float('inf'),    # Practically unlimited
            'xfs': float('inf'),     # Practically unlimited
            'ntfs': float('inf'),    # Practically unlimited
            'apfs': float('inf'),    # Practically unlimited
            'hfs+': float('inf'),    # Practically unlimited
            'btrfs': float('inf'),   # Practically unlimited
            'zfs': float('inf'),     # Practically unlimited
        }
        return max_sizes.get(fstype.lower(), float('inf'))
        
    def _calculate_hash(self, file_path: Path, chunk_size: Optional[int] = None) -> str:
        """Calculate SHA256 hash of a file."""
        if chunk_size is None:
            chunk_size = self.chunk_size
            
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except (OSError, IOError) as e:
            raise RuntimeError(f"Failed to calculate hash for {file_path}: {e}")
            
    def _should_exclude(self, file_path: Path) -> bool:
        """Check if file should be excluded based on patterns."""
        file_name = file_path.name
        for pattern in self.exclusion_patterns:
            if pattern.startswith('*'):
                if file_name.endswith(pattern[1:]):
                    return True
            elif pattern.endswith('*'):
                if file_name.startswith(pattern[:-1]):
                    return True
            elif file_name == pattern:
                return True
        return False
        
    def _get_relative_path(self, file_path: Path) -> str:
        """Get relative path from source directory."""
        return str(file_path.relative_to(self.source_dir))
        
    def _is_drive_accessible(self) -> bool:
        """Check if the destination drive is accessible."""
        try:
            # Try to access the destination directory
            if not self.destination_dir.exists():
                return False
            
            # macOS-specific check for external drive availability
            if self.is_macos:
                return self._check_macos_drive_mounted()
            
            # Try to create a small test file to check if drive is writable
            test_file = self.destination_dir / ".archiving_tool_test"
            test_file.write_text("test")
            test_file.unlink()
            return True
        except (OSError, IOError, PermissionError):
            return False
            
    def _is_source_accessible(self) -> bool:
        """Check if the source directory is accessible (especially important for network paths)."""
        try:
            # Try to access the source directory
            if not self.source_dir.exists():
                return False
            
            # Try to list the directory to ensure network connectivity
            list(self.source_dir.iterdir())
            return True
        except (OSError, IOError, PermissionError):
            return False
            
    def _is_network_error(self, error: Exception) -> bool:
        """Check if an error is network-related (SMB, NFS, etc.)."""
        error_msg = str(error).lower()
        network_indicators = [
            'socket is not connected',  # SMB disconnection
            'connection refused',
            'connection reset',
            'network is unreachable',
            'host is unreachable',
            'timeout',
            'connection timed out',
            'connection lost',
            'no route to host',
            'connection aborted',
            'broken pipe',
            'smb',
            'cifs',
            'nfs'
        ]
        
        # Check error message
        for indicator in network_indicators:
            if indicator in error_msg:
                return True
                
        # Check errno values for network-related errors
        if hasattr(error, 'errno'):
            network_errnos = {
                57,   # ENOTCONN (Socket is not connected)
                61,   # ECONNREFUSED (Connection refused)
                64,   # EHOSTDOWN (Host is down)
                65,   # EHOSTUNREACH (No route to host)
                104,  # ECONNRESET (Connection reset by peer)
                110,  # ETIMEDOUT (Connection timed out)
                111,  # ECONNREFUSED (Connection refused)
                113,  # EHOSTUNREACH (No route to host)
            }
            if error.errno in network_errnos:
                return True
                
        return False
        
    def _show_network_troubleshooting_tips(self) -> None:
        """Display helpful troubleshooting tips for network connectivity issues."""
        print("\n" + "=" * 60)
        print("NETWORK CONNECTIVITY TROUBLESHOOTING TIPS")
        print("=" * 60)
        print("If you're experiencing network connectivity issues:")
        print()
        print("1. SMB/CIFS Shares:")
        print("   - The tool will automatically attempt to remount disconnected SMB shares")
        print("   - Check if the share is still mounted: mount | grep cifs")
        print("   - Manual remount: sudo umount /path && sudo mount -t cifs //server/share /path")
        print("   - Verify network connectivity to the server")
        print()
        print("2. NFS Shares:")
        print("   - Check mount status: mount | grep nfs")
        print("   - Try remounting: sudo umount /path && sudo mount -t nfs server:/path /path")
        print()
        print("3. General Network Issues:")
        print("   - Check network connection: ping <server-ip>")
        print("   - Verify DNS resolution: nslookup <server-name>")
        print("   - Check firewall settings")
        print()
        print("4. Resume Options:")
        print("   - Use 'resume' command to continue from where it stopped")
        print("   - The tool automatically saves progress and can resume interrupted operations")
        print("=" * 60)
        print()
        
    def _is_network_path(self, path: Path) -> bool:
        """Check if a path is likely a network path (SMB, NFS, etc.)."""
        path_str = str(path).lower()
        
        # Common network path indicators
        network_indicators = [
            '///',           # SMB paths on Linux
            '//',            # UNC paths  
            'smb://',        # SMB protocol
            'nfs://',        # NFS protocol
            'ftp://',        # FTP protocol
            'sftp://',       # SFTP protocol
        ]
        
        for indicator in network_indicators:
            if indicator in path_str:
                return True
                
        # Check if path starts with /mnt/ (common mount point)
        if path_str.startswith('/mnt/'):
            return True
            
        # Check if path is in common network mount locations
        network_mount_prefixes = ['/media/', '/run/media/', '/volumes/']
        for prefix in network_mount_prefixes:
            if path_str.startswith(prefix):
                return True
                
        return False
        
    def _get_mount_info(self, path: Path) -> Optional[Dict]:
        """Get mount information for a given path."""
        try:
            import subprocess
            # Use findmnt to get mount information
            result = subprocess.run(
                ['findmnt', '-T', str(path), '-o', 'SOURCE,FSTYPE,OPTIONS', '-n'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split()
                if len(parts) >= 2:
                    return {
                        'source': parts[0],
                        'fstype': parts[1],
                        'options': parts[2] if len(parts) > 2 else '',
                        'mountpoint': str(path)
                    }
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return None
        
    def _is_smb_mount(self, path: Path) -> bool:
        """Check if the path is mounted as SMB/CIFS."""
        mount_info = self._get_mount_info(path)
        if mount_info:
            fstype = mount_info.get('fstype', '').lower()
            return fstype in ['cifs', 'smb', 'smbfs']
        return False
        
    def _get_smb_mount_command(self, path: Path) -> Optional[str]:
        """Generate the mount command to remount an SMB share."""
        mount_info = self._get_mount_info(path)
        if not mount_info:
            return None
            
        fstype = mount_info.get('fstype', '').lower()
        if fstype not in ['cifs', 'smb', 'smbfs']:
            return None
            
        source = mount_info.get('source', '')
        options = mount_info.get('options', '')
        
        # Clean up options - remove some that might cause issues on remount
        if options:
            # Remove options that might cause problems on remount
            option_list = [opt for opt in options.split(',') 
                          if not opt.startswith(('_netdev', 'user'))]
            clean_options = ','.join(option_list) if option_list else ''
        else:
            clean_options = ''
            
        # Construct mount command
        if clean_options:
            mount_cmd = f"sudo mount -t cifs '{source}' '{path}' -o {clean_options}"
        else:
            mount_cmd = f"sudo mount -t cifs '{source}' '{path}'"
            
        return mount_cmd
        
    def _attempt_smb_reconnection(self, path: Path) -> bool:
        """Attempt to reconnect an SMB share by unmounting and remounting."""
        try:
            import subprocess
            
            print(f"Attempting to reconnect SMB share at {path}...")
            
            # First, try to get mount information before unmounting
            mount_cmd = self._get_smb_mount_command(path)
            if not mount_cmd:
                print("Could not determine mount command for SMB share")
                return False
            
            # Step 1: Unmount (with force if needed)
            print("Unmounting SMB share...")
            try:
                # Try graceful unmount first
                result = subprocess.run(
                    ['sudo', 'umount', str(path)],
                    capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    # If graceful unmount fails, try force unmount
                    print("Graceful unmount failed, trying force unmount...")
                    result = subprocess.run(
                        ['sudo', 'umount', '-f', str(path)],
                        capture_output=True, text=True, timeout=30
                    )
                    if result.returncode != 0:
                        # If even force unmount fails, try lazy unmount
                        print("Force unmount failed, trying lazy unmount...")
                        subprocess.run(
                            ['sudo', 'umount', '-l', str(path)],
                            capture_output=True, text=True, timeout=30
                        )
            except subprocess.TimeoutExpired:
                print("Unmount operation timed out")
                return False
            
            # Step 2: Wait a moment for cleanup
            time.sleep(2)
            
            # Step 3: Remount
            print(f"Remounting SMB share...")
            print(f"Using command: {mount_cmd}")
            
            # Execute the mount command
            result = subprocess.run(
                mount_cmd, shell=True, capture_output=True, text=True, timeout=60
            )
            
            if result.returncode == 0:
                print("SMB share remounted successfully!")
                # Verify the mount worked
                time.sleep(1)
                if self._is_source_accessible():
                    return True
                else:
                    print("Mount appeared successful but source is still not accessible")
                    return False
            else:
                error_msg = result.stderr.strip()
                print(f"Failed to remount SMB share: {error_msg}")
                
                # If sudo failed, suggest manual intervention
                if "sudo" in error_msg or "permission" in error_msg.lower():
                    print("\nNote: Automatic remounting requires sudo privileges.")
                    print("You may need to manually remount the SMB share:")
                    print(f"  {mount_cmd}")
                    print("Or ensure the share is configured in /etc/fstab for automatic mounting.")
                    
                return False
                
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            print(f"Error during SMB reconnection: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error during SMB reconnection: {e}")
            return False
            
    def _attempt_network_reconnection(self, path: Path) -> bool:
        """Attempt to actively reconnect a network mount."""
        if self._is_smb_mount(path):
            return self._attempt_smb_reconnection(path)
        else:
            # For other network filesystems, we can add support later
            print(f"Active reconnection not yet supported for this filesystem type")
            return False
            
    def reconnect_network_source(self) -> bool:
        """Manually attempt to reconnect the network source.
        
        This method can be called directly by users when they want to 
        manually trigger a reconnection attempt.
        
        Returns:
            True if reconnection succeeded, False otherwise
        """
        if not self.is_network_source:
            print("Source is not detected as a network path")
            return False
            
        print(f"Attempting manual reconnection of network source: {self.source_dir}")
        
        if self._attempt_network_reconnection(self.source_dir):
            if self._is_source_accessible():
                print("Manual reconnection successful!")
                return True
            else:
                print("Reconnection appeared successful but source is still not accessible")
                return False
        else:
            print("Manual reconnection failed")
            self._show_network_troubleshooting_tips()
            return False
            
    def _check_macos_drive_mounted(self) -> bool:
        """Check if external drive is properly mounted on macOS."""
        try:
            # Check if the destination path exists first
            if not self.destination_dir.exists():
                return False

            # Check if the destination path is on a mounted volume
            result = subprocess.run(
                ['diskutil', 'info', str(self.destination_dir)], 
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                output = result.stdout.lower()
                
                # Check both mounted status and write protection
                is_mounted = 'mounted' in output and 'yes' in output
                is_writable = 'write-protected' not in output or ('write-protected' in output and 'no' in output)
                
                if is_mounted and is_writable:
                    # Verify we can actually write to the destination
                    test_file = self.destination_dir / ".archiving_tool_test"
                    test_file.write_text("test")
                    test_file.unlink()
                    return True
            return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, IOError):
            return False
            
    def _detect_apfs_filesystem(self) -> bool:
        """Detect if destination is on APFS filesystem (macOS only)."""
        if not self.is_macos:
            return False
            
        try:
            import subprocess
            result = subprocess.run(
                ['diskutil', 'info', str(self.destination_dir)], 
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return 'APFS' in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass
        return False
        
    def _optimize_for_apfs(self) -> None:
        """Apply APFS-specific optimizations."""
        if self._detect_apfs_filesystem():
            # APFS benefits from larger chunk sizes for better performance
            self.chunk_size = 2 * 1024 * 1024  # 2MB chunks for APFS
            print("Detected APFS filesystem - optimizing for better performance")
            
    def _preserve_macos_metadata(self, source_path: Path, dest_path: Path) -> bool:
        """Preserve macOS extended attributes and metadata."""
        if not self.is_macos:
            return True
            
        try:
            import subprocess
            # Copy extended attributes using xattr
            result = subprocess.run(
                ['xattr', '-l', str(source_path)], 
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                # Copy extended attributes
                subprocess.run(
                    ['xattr', '-w', str(source_path), str(dest_path)], 
                    timeout=10, check=False
                )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            # Non-critical - continue without extended attributes
            return True
            
    def _wait_for_drive_reconnection(self, max_wait_time: int = 60) -> bool:
        """Wait for drive to reconnect with intelligent retry intervals.
        
        Args:
            max_wait_time: Maximum time to wait in seconds
            
        Returns:
            True if drive becomes accessible, False if timeout reached
        """
        wait_intervals = [2, 5, 10, 15, 30]  # Progressive wait times
        total_waited = 0
        
        for interval in wait_intervals:
            if total_waited >= max_wait_time:
                return False
                
            print(f"Waiting {interval}s for drive reconnection...")
            time.sleep(interval)
            total_waited += interval
            
            if self._is_drive_accessible():
                print("Drive reconnected successfully!")
                return True
                
        # Final wait with remaining time
        remaining_time = max_wait_time - total_waited
        if remaining_time > 0:
            print(f"Final wait of {remaining_time}s for drive reconnection...")
            time.sleep(remaining_time)
            if self._is_drive_accessible():
                print("Drive reconnected successfully!")
                return True
                
        print(f"Drive did not reconnect within {max_wait_time}s timeout")
        return False
        
    def _wait_for_network_reconnection(self, max_wait_time: int = 120) -> bool:
        """Wait for network source to reconnect with intelligent retry intervals.
        
        Network connections (like SMB) often need longer to reconnect than local drives.
        This method also attempts active reconnection for supported network filesystems.
        
        Args:
            max_wait_time: Maximum time to wait in seconds (default 2 minutes for networks)
            
        Returns:
            True if source becomes accessible, False if timeout reached
        """
        wait_intervals = [5, 10, 15, 30, 60]  # Longer intervals for network recovery
        total_waited = 0
        attempted_active_reconnection = False
        
        print(f"Network source appears disconnected. Waiting for reconnection...")
        
        for interval in wait_intervals:
            if total_waited >= max_wait_time:
                break
            
            # Attempt active reconnection on the second iteration (after first wait)
            if not attempted_active_reconnection and total_waited > 0:
                attempted_active_reconnection = True
                print("Attempting active network reconnection...")
                if self._attempt_network_reconnection(self.source_dir):
                    # Check if reconnection was successful
                    if self._is_source_accessible():
                        print("Active reconnection successful!")
                        return True
                    else:
                        print("Active reconnection appeared to succeed but source still not accessible")
                else:
                    print("Active reconnection failed, continuing with passive waiting...")
            
            print(f"Waiting {interval}s for network reconnection...")
            time.sleep(interval)
            total_waited += interval
            
            if self._is_source_accessible():
                print("Network source reconnected successfully!")
                return True
                
        # Final attempt at active reconnection if not tried yet
        if not attempted_active_reconnection:
            print("Final attempt at active network reconnection...")
            if self._attempt_network_reconnection(self.source_dir):
                if self._is_source_accessible():
                    print("Final active reconnection successful!")
                    return True
                    
        # Final wait with remaining time
        remaining_time = max_wait_time - total_waited
        if remaining_time > 0:
            print(f"Final wait of {remaining_time}s for network reconnection...")
            time.sleep(remaining_time)
            if self._is_source_accessible():
                print("Network source reconnected successfully!")
                return True
                
        print(f"Network source did not reconnect within {max_wait_time}s timeout")
        return False
            
    def _copy_with_macos_optimization(self, source_path: Path, dest_path: Path) -> None:
        """Use macOS-optimized copy operations."""
        try:
            import subprocess
            # Try using macOS's optimized cp command with APFS optimizations
            result = subprocess.run(
                ['cp', '-a', str(source_path), str(dest_path)], 
                timeout=600,  # 10 minute timeout for large files
                check=True
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            # Fall back to Python's shutil if cp fails
            shutil.copy2(source_path, dest_path)
            
    def _copy_file_with_retry(self, source_path: Path, dest_path: Path, file_info: Dict) -> bool:
        """Copy a single file with retry logic for drive and network issues.
        
        The retry mechanism works by using a for loop that repeats the entire copy operation
        up to max_retries + 1 times. When an exception occurs (copy failure or verification
        failure), the exception handler performs cleanup and uses 'continue' to restart the
        loop from the beginning, which triggers a new copy attempt.
        
        Enhanced for network sources (SMB, NFS, etc.) with longer timeouts and 
        network-specific error detection.
        
        Performance optimization: Drive accessibility is only checked AFTER a copy failure,
        not before every copy attempt, to avoid unnecessary overhead when copying many files.
        
        Args:
            source_path: Source file path
            dest_path: Destination file path
            file_info: File metadata from manifest
            
        Returns:
            True if copy succeeded, False if all retries failed
        """
        for attempt in range(self.max_retries + 1):  # +1 for initial attempt
            try:
                # Create destination directory
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Check if we need chunked copy for large files
                file_size = source_path.stat().st_size
                use_chunked_copy = file_size > (2 * 1024 * 1024 * 1024)  # 2GB threshold
                
                # Check filesystem limits
                max_filesize = self._get_filesystem_max_filesize(self.dest_filesystem)
                if file_size > max_filesize:
                    fs_name = self.dest_filesystem or "the destination filesystem"
                    raise OSError(75, f"File is larger than {self._format_size(max_filesize)} and cannot be copied to {fs_name}: {source_path}")
                    
                if use_chunked_copy:
                    # Use chunked copy for large files (but still under 4GB)
                    with open(source_path, 'rb') as src, open(dest_path, 'wb') as dst:
                        while True:
                            chunk = src.read(8 * 1024 * 1024)  # 8MB chunks
                            if not chunk:
                                break
                            dst.write(chunk)
                    # Copy metadata separately
                    shutil.copystat(source_path, dest_path)
                else:
                    # Use normal copy for smaller files
                    if self.is_macos:
                        # Use macOS-optimized copy if available
                        self._copy_with_macos_optimization(source_path, dest_path)
                    else:
                        shutil.copy2(source_path, dest_path)
                
                # Preserve macOS metadata if needed
                if self.is_macos:
                    self._preserve_macos_metadata(source_path, dest_path)
                
                # Verify copy
                dest_hash = self._calculate_hash(dest_path)
                if dest_hash != file_info['hash']:
                    # Hash mismatch could indicate corruption during copy
                    if attempt < self.max_retries:
                        print(f"Hash mismatch after copy, retrying... (attempt {attempt + 1}/{self.max_retries + 1})")
                        # Remove corrupted file
                        if dest_path.exists():
                            dest_path.unlink()
                        time.sleep(self.retry_delay)
                        continue
                    else:
                        print(f"Error: Hash mismatch after {self.max_retries + 1} attempts for {source_path}")
                        return False
                
                # Success
                return True
                
            except (OSError, IOError, PermissionError) as e:
                # Check if this is a network-related error
                is_network_error = self._is_network_error(e)
                if attempt < self.max_retries:
                    if is_network_error:
                        print(f"Network error detected ({e}), waiting for network reconnection... (attempt {attempt + 1}/{self.max_retries + 1})")
                        # Wait longer for network reconnection
                        if not self._wait_for_network_reconnection():
                            print(f"Network still not accessible, continuing retry... (attempt {attempt + 1}/{self.max_retries + 1})")
                    else:
                        # Check if destination drive is accessible only after a non-network failure
                        if not self._is_drive_accessible():
                            print(f"Destination drive not accessible after copy failure, waiting for reconnection... (attempt {attempt + 1}/{self.max_retries + 1})")
                            # Wait for drive reconnection
                            if not self._wait_for_drive_reconnection():
                                print(f"Drive still not accessible, continuing retry... (attempt {attempt + 1}/{self.max_retries + 1})")
                        else:
                            print(f"Copy failed ({e}), retrying in {self.retry_delay}s... (attempt {attempt + 1}/{self.max_retries + 1})")
                            time.sleep(self.retry_delay)
                    
                    # Clean up partial file if it exists
                    if dest_path.exists():
                        try:
                            dest_path.unlink()
                        except:
                            pass
                    continue
                else:
                    error_type = "Network error" if is_network_error else "Copy error"
                    print(f"Error: {error_type} after {self.max_retries + 1} attempts for {source_path}: {e}")
                    return False
            except RuntimeError as e:
                # Hash calculation error - could indicate network or drive issue
                if attempt < self.max_retries:
                    print(f"Verification failed ({e}), retrying... (attempt {attempt + 1}/{self.max_retries + 1})")
                    
                    # Check both source and destination accessibility
                    source_accessible = self._is_source_accessible()
                    dest_accessible = self._is_drive_accessible()
                    
                    if not source_accessible:
                        print("Source accessibility issue detected, waiting for network reconnection...")
                        if not self._wait_for_network_reconnection():
                            print("Source still not accessible, continuing retry...")
                    elif not dest_accessible:
                        print("Destination accessibility issue detected, waiting for drive reconnection...")
                        if not self._wait_for_drive_reconnection():
                            print("Destination still not accessible, continuing retry...")
                    else:
                        time.sleep(self.retry_delay)
                    
                    # Clean up partial file if it exists  
                    if dest_path.exists():
                        try:
                            dest_path.unlink()
                        except:
                            pass
                    continue
                else:
                    print(f"Error: Verification failed after {self.max_retries + 1} attempts for {source_path}: {e}")
                    return False
            
        return False
        
    def _save_progress_state(self, manifest: Dict, completed_files: List[str], failed_files: List[str]) -> bool:
        """Save progress state for resuming interrupted operations.
        
        Args:
            manifest: Current manifest
            completed_files: List of relative paths that were successfully copied
            failed_files: List of relative paths that failed to copy
            
        Returns:
            True if progress was saved successfully
        """
        try:
            progress_file = self.destination_dir / ".archiving_tool_progress.json"
            progress_data = {
                'timestamp': datetime.now().isoformat(),
                'operation': 'copy',
                'completed_files': completed_files,
                'failed_files': failed_files,
                'manifest_snapshot': manifest
            }
            
            with open(progress_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
            return True
        except (OSError, IOError) as e:
            print(f"Warning: Could not save progress state: {e}")
            return False
            
    def _load_progress_state(self) -> Optional[Dict]:
        """Load progress state from previous interrupted operation."""
        try:
            progress_file = self.destination_dir / ".archiving_tool_progress.json"
            if not progress_file.exists():
                return None
                
            with open(progress_file, 'r') as f:
                return json.load(f)
        except (OSError, IOError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load progress state: {e}")
            return None
            
    def _save_skipped_file(self, rel_path: str, size: int, reason: str) -> None:
        """Save information about a file that was skipped during copy.
        
        Args:
            rel_path: Relative path of the skipped file
            size: Size of the file in bytes
            reason: Reason why the file was skipped
        """
        skipped_file = self.destination_dir / ".archiving_tool_skipped.json"
        try:
            if skipped_file.exists():
                with open(skipped_file, 'r') as f:
                    skipped_data = json.load(f)
            else:
                skipped_data = {
                    'skipped_files': {},
                    'total_size': 0,
                    'count': 0
                }
            
            # Add or update skipped file info
            skipped_data['skipped_files'][rel_path] = {
                'size': size,
                'reason': reason,
                'timestamp': datetime.now().isoformat()
            }
            
            # Update totals
            skipped_data['total_size'] = sum(f['size'] for f in skipped_data['skipped_files'].values())
            skipped_data['count'] = len(skipped_data['skipped_files'])
            
            # Save updated skipped files list
            with open(skipped_file, 'w') as f:
                json.dump(skipped_data, f, indent=2)
                
        except (OSError, IOError, json.JSONDecodeError) as e:
            print(f"Warning: Could not save skipped file information: {e}")
            
    def get_skipped_files(self) -> Dict:
        """Get information about files that were skipped during copy.
        
        Returns:
            Dictionary containing information about skipped files and their reasons
        """
        skipped_file = self.destination_dir / ".archiving_tool_skipped.json"
        try:
            if skipped_file.exists():
                with open(skipped_file, 'r') as f:
                    return json.load(f)
            return {'skipped_files': {}, 'total_size': 0, 'count': 0}
        except (OSError, IOError, json.JSONDecodeError) as e:
            print(f"Warning: Could not load skipped files information: {e}")
            return {'skipped_files': {}, 'total_size': 0, 'count': 0}
            
    def _clear_progress_state(self) -> None:
        """Clear progress state file after successful completion."""
        try:
            progress_file = self.destination_dir / ".archiving_tool_progress.json"
            if progress_file.exists():
                progress_file.unlink()
        except (OSError, IOError):
            pass  # Not critical if we can't remove it
        
    def _scan_directory(self, directory: Path, description: str = "Scanning") -> List[Dict]:
        """Scan directory and return file information."""
        files_info = []
        
        # Get all files first for progress bar
        all_files = []
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = Path(root) / file
                if not self._should_exclude(file_path):
                    all_files.append(file_path)
                    
        # Process files with progress bar
        for file_path in tqdm(all_files, desc=description, unit="files"):
            try:
                stat = file_path.stat()
                file_hash = self._calculate_hash(file_path)
                
                file_info = {
                    'relative_path': self._get_relative_path(file_path),
                    'size': stat.st_size,
                    'mtime': stat.st_mtime,
                    'hash': file_hash,
                    'last_verified': time.time()
                }
                files_info.append(file_info)
                
            except (OSError, IOError, RuntimeError) as e:
                print(f"Warning: Skipping {file_path}: {e}")
                continue
                
        return files_info
        
    def init(self, force: bool = False) -> bool:
        """Initialize the archive by creating a manifest of all source files.
        
        Args:
            force: Overwrite existing manifest if it exists
            
        Returns:
            True if successful, False otherwise
        """
        if self.manifest_file.exists() and not force:
            print(f"Manifest already exists at {self.manifest_file}")
            print("Use --force to overwrite or run 'update' to add new files")
            return False
            
        if not self.source_dir.exists():
            print(f"Error: Source directory {self.source_dir} does not exist")
            return False
            
        print(f"Initializing archive from {self.source_dir}")
        print(f"Destination: {self.destination_dir}")
        print(f"Manifest: {self.manifest_file}")
        
        # Apply macOS/APFS optimizations
        if self.is_macos:
            self._optimize_for_apfs()
        
        # Create destination directory if it doesn't exist
        self.destination_dir.mkdir(parents=True, exist_ok=True)
        
        # Scan source directory
        files_info = self._scan_directory(self.source_dir, "Scanning source files")
        
        # Create manifest
        print("Creating manifest...")
        manifest = {
            'created': datetime.now().isoformat(),
            'source_dir': str(self.source_dir),
            'destination_dir': str(self.destination_dir),
            'total_files': len(files_info),
            'total_size': sum(f['size'] for f in files_info),
            'files': {}
        }
        
        # Build file dictionary with progress bar
        for file_info in tqdm(files_info, desc="Building manifest", unit="files"):
            manifest['files'][file_info['relative_path']] = file_info
        
        # Save manifest
        print("Saving manifest...")
        with open(self.manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)
            
        print(f"\nManifest created successfully!")
        print(f"Total files: {len(files_info)}")
        print(f"Total size: {self._format_size(manifest['total_size'])}")
        
        return True
        
    def _load_manifest(self) -> Optional[Dict]:
        """Load the manifest file."""
        if not self.manifest_file.exists():
            print(f"Error: Manifest file {self.manifest_file} does not exist")
            print("Run 'init' first to create the manifest")
            return None
            
        try:
            with open(self.manifest_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"Error loading manifest: {e}")
            return None
            
    def _save_manifest(self, manifest: Dict) -> bool:
        """Save the manifest file."""
        try:
            with open(self.manifest_file, 'w') as f:
                json.dump(manifest, f, indent=2)
            return True
        except OSError as e:
            print(f"Error saving manifest: {e}")
            return False
            
    def copy(self, dry_run: bool = False) -> bool:
        """Copy files from source to destination based on manifest.
        
        Args:
            dry_run: Show what would be copied without actually copying
            
        Returns:
            True if successful, False otherwise
        """
        manifest = self._load_manifest()
        if not manifest:
            return False
            
        files_to_copy = []
        files_to_verify = []
        
        # Check which files need copying with progress bar
        print("Checking which files need copying...")
        for rel_path, file_info in tqdm(manifest['files'].items(), desc="Analyzing files", unit="files"):
            source_path = self.source_dir / rel_path
            dest_path = self.destination_dir / rel_path
            
            if not source_path.exists():
                tqdm.write(f"Warning: Source file missing: {source_path}")
                continue
                
            # Check if file size exceeds filesystem limits
            max_filesize = self._get_filesystem_max_filesize(self.dest_filesystem)
            if file_info['size'] > max_filesize:
                fs_name = self.dest_filesystem or "unknown"
                tqdm.write(f"Warning: Skipping file larger than {self._format_size(max_filesize)} ({fs_name} limit): {rel_path}")
                self._save_skipped_file(rel_path, file_info['size'], f"File too large for {fs_name} filesystem (limit: {self._format_size(max_filesize)})")
                continue
                
            needs_copy = False
            if not dest_path.exists():
                needs_copy = True
            else:
                # Check if destination file matches
                try:
                    dest_hash = self._calculate_hash(dest_path)
                    if dest_hash != file_info['hash']:
                        needs_copy = True
                        tqdm.write(f"Hash mismatch for {rel_path}, will re-copy")
                except RuntimeError:
                    needs_copy = True
                    tqdm.write(f"Cannot verify {rel_path}, will re-copy")
                    
            if needs_copy:
                files_to_copy.append((source_path, dest_path, file_info))
            else:
                files_to_verify.append((dest_path, file_info))
                
        if not files_to_copy and not files_to_verify:
            print("No files to copy or verify")
            return True
            
        print(f"Files to copy: {len(files_to_copy)}")
        print(f"Files to verify: {len(files_to_verify)}")
        
        if dry_run:
            print("\nDry run - would copy:")
            for source_path, dest_path, _ in files_to_copy:
                print(f"  {source_path} -> {dest_path}")
            return True
            
        # Copy files
        if files_to_copy:
            print("\nCopying files...")
            completed_files = []
            failed_files = []
            
            # Initial source accessibility check (important for network sources)
            if not self._is_source_accessible():
                print("Error: Source directory is not accessible")
                if self.is_network_source:
                    print("This appears to be a network source (SMB, NFS, etc.)")
                    print("Network connectivity issue detected!")
                    self._show_network_troubleshooting_tips()
                else:
                    print("Please check that the source directory exists and is accessible")
                return False
            
                # Initial drive accessibility check (only once at start)
            if not self._is_drive_accessible():
                print("Error: Destination drive is not accessible")
                print(f"Destination path: {self.destination_dir}")
                
                if self.is_macos:
                    # For macOS, check if drive is properly mounted
                    if not self._check_macos_drive_mounted():
                        print("\nDrive appears to be unmounted or improperly mounted.")
                        print("Troubleshooting tips:")
                        print("1. Check if the drive appears in Finder")
                        print("2. Try safely ejecting and reconnecting the drive")
                        print("3. Verify the drive mounts properly in Disk Utility")
                        print("4. Check system logs for potential I/O errors (Console.app)")
                    else:
                        print("\nDrive is mounted but may have permission issues.")
                        print("Troubleshooting tips:")
                        print("1. Check drive permissions in Finder (Get Info)")
                        print("2. Try running the tool with sudo if needed")
                        print("3. Verify the drive is not in read-only mode")
                
                return False            # Calculate total size for progress tracking
            total_copy_size = sum(file_info['size'] for _, _, file_info in files_to_copy)
            
            # Check for previous progress
            progress_state = self._load_progress_state()
            if progress_state and not dry_run:
                print(f"Found previous progress state from {progress_state['timestamp']}")
                completed_files = progress_state.get('completed_files', [])
                if completed_files:
                    print(f"Skipping {len(completed_files)} already completed files")
                    # Filter out already completed files
                    files_to_copy = [(s, d, f) for s, d, f in files_to_copy 
                                   if self._get_relative_path(s) not in completed_files]
                    # Recalculate remaining size
                    total_copy_size = sum(file_info['size'] for _, _, file_info in files_to_copy)
            
            progress_bar = self._create_progress_bar(
                files_to_copy, 
                "Copying", 
                "files", 
                total_copy_size
            )
            
            try:
                for source_path, dest_path, file_info in progress_bar:
                    rel_path = self._get_relative_path(source_path)
                    
                    if self._copy_file_with_retry(source_path, dest_path, file_info):
                        completed_files.append(rel_path)
                    else:
                        failed_files.append(rel_path)
                        # Save progress before aborting
                        self._save_progress_state(manifest, completed_files, failed_files)
                        print(f"\nCopy operation aborted due to persistent failures.")
                        print(f"Successfully copied: {len(completed_files)} files")
                        print(f"Failed to copy: {len(failed_files)} files")
                        print(f"Failed files: {failed_files}")
                        print(f"Run the copy command again to resume from where it left off.")
                        
                        # Show network troubleshooting tips if this appears to be a network source
                        if self.is_network_source:
                            self._show_network_troubleshooting_tips()
                        
                        return False
                        
                # Clear progress state on successful completion
                self._clear_progress_state()
            except Exception as e:
                # Save progress for any unexpected exception (KeyboardInterrupt, MemoryError, etc.)
                self._save_progress_state(manifest, completed_files, failed_files)
                print(f"\nCopy operation interrupted by unexpected error: {e}")
                print(f"Successfully copied: {len(completed_files)} files")
                print(f"Failed to copy: {len(failed_files)} files")
                print(f"Progress has been saved. Run the copy command again to resume from where it left off.")
                
                # Show network troubleshooting tips if this appears to be a network source
                if self.is_network_source:
                    self._show_network_troubleshooting_tips()
                
                return False
                    
        # Verify existing files
        if files_to_verify:
            print("\nVerifying existing files...")
            total_verify_size = sum(file_info['size'] for _, file_info in files_to_verify)
            progress_bar = self._create_progress_bar(
                files_to_verify, 
                "Verifying", 
                "files", 
                total_verify_size
            )
            
            for dest_path, file_info in progress_bar:
                try:
                    dest_hash = self._calculate_hash(dest_path)
                    if dest_hash != file_info['hash']:
                        print(f"Error: Hash mismatch for existing file {dest_path}")
                        return False
                except RuntimeError as e:
                    print(f"Error verifying {dest_path}: {e}")
                    return False
                    
        print("\nCopy operation completed successfully!")
        return True
        
    def update(self, dry_run: bool = False) -> bool:
        """Update manifest with new and modified files, then copy them.
        
        Args:
            dry_run: Show what would be updated without actually doing it
            
        Returns:
            True if successful, False otherwise
        """
        manifest = self._load_manifest()
        if not manifest:
            return False
            
        print("Scanning for new and modified files...")
        current_files = self._scan_directory(self.source_dir, "Scanning source files")
        
        # Convert to dict for easier lookup
        current_files_dict = {f['relative_path']: f for f in current_files}
        manifest_files = manifest['files']
        
        # Find new and modified files
        new_files = []
        modified_files = []
        deleted_files = []
        
        # Check for new and modified files with progress
        print("Comparing files with manifest...")
        for rel_path, file_info in tqdm(current_files_dict.items(), desc="Checking for changes", unit="files"):
            # Check if file size exceeds filesystem limits
            max_filesize = self._get_filesystem_max_filesize(self.dest_filesystem)
            if file_info['size'] > max_filesize:
                fs_name = self.dest_filesystem or "unknown"
                tqdm.write(f"Warning: Skipping file larger than {self._format_size(max_filesize)} ({fs_name} limit): {rel_path}")
                self._save_skipped_file(rel_path, file_info['size'], f"File too large for {fs_name} filesystem (limit: {self._format_size(max_filesize)})")
                continue
                
            if rel_path not in manifest_files:
                new_files.append(rel_path)
            elif (manifest_files[rel_path]['hash'] != file_info['hash'] or 
                  manifest_files[rel_path]['mtime'] != file_info['mtime']):
                modified_files.append(rel_path)
                
        # Check for deleted files with progress
        for rel_path in tqdm(manifest_files, desc="Checking for deletions", unit="files"):
            if rel_path not in current_files_dict:
                deleted_files.append(rel_path)
                
        print(f"\nNew files: {len(new_files)}")
        print(f"Modified files: {len(modified_files)}")
        print(f"Deleted files: {len(deleted_files)}")
        
        if not new_files and not modified_files and not deleted_files:
            print("No changes detected")
            return True
            
        if dry_run:
            if new_files:
                print("\nNew files:")
                for path in new_files[:10]:  # Show first 10
                    print(f"  + {path}")
                if len(new_files) > 10:
                    print(f"  ... and {len(new_files) - 10} more")
                    
            if modified_files:
                print("\nModified files:")
                for path in modified_files[:10]:  # Show first 10
                    print(f"  * {path}")
                if len(modified_files) > 10:
                    print(f"  ... and {len(modified_files) - 10} more")
                    
            if deleted_files:
                print("\nDeleted files:")
                for path in deleted_files[:10]:  # Show first 10
                    print(f"  - {path}")
                if len(deleted_files) > 10:
                    print(f"  ... and {len(deleted_files) - 10} more")
            return True
            
        # Update manifest with progress bars
        print("Updating manifest...")
        update_items = new_files + modified_files
        for rel_path in tqdm(update_items, desc="Adding/updating entries", unit="files"):
            manifest_files[rel_path] = current_files_dict[rel_path]
            
        for rel_path in tqdm(deleted_files, desc="Removing deleted entries", unit="files"):
            del manifest_files[rel_path]
            
        # Update manifest metadata
        print("Updating manifest metadata...")
        manifest['total_files'] = len(manifest_files)
        manifest['total_size'] = sum(f['size'] for f in manifest_files.values())
        manifest['last_updated'] = datetime.now().isoformat()
        
        # Save updated manifest
        if not self._save_manifest(manifest):
            return False
            
        print("Manifest updated successfully!")
        
        # Copy new and modified files
        if new_files or modified_files:
            print("\nCopying new and modified files...")
            files_to_copy = new_files + modified_files
            completed_files = []
            failed_files = []
            
            # Initial source accessibility check (important for network sources)
            if not self._is_source_accessible():
                print("Error: Source directory is not accessible")
                if self.is_network_source:
                    print("This appears to be a network source (SMB, NFS, etc.)")
                    print("Network connectivity issue detected!")
                    self._show_network_troubleshooting_tips()
                else:
                    print("Please check that the source directory exists and is accessible")
                return False
            
            # Calculate total size for progress tracking
            total_copy_size = sum(manifest_files[rel_path]['size'] for rel_path in files_to_copy)
            progress_bar = self._create_progress_bar(
                files_to_copy,
                "Copying updates",
                "files",
                total_copy_size
            )
            
            try:
                for rel_path in progress_bar:
                    source_path = self.source_dir / rel_path
                    dest_path = self.destination_dir / rel_path
                    file_info = manifest_files[rel_path]
                    
                    if self._copy_file_with_retry(source_path, dest_path, file_info):
                        completed_files.append(rel_path)
                    else:
                        failed_files.append(rel_path)
                        # Save progress before aborting
                        self._save_progress_state(manifest, completed_files, failed_files)
                        print(f"\nUpdate operation aborted due to persistent failures.")
                        print(f"Successfully copied: {len(completed_files)} files")
                        print(f"Failed to copy: {len(failed_files)} files")
                        print(f"Failed files: {failed_files}")
                        print(f"Run the update command again to resume from where it left off.")
                        
                        # Show network troubleshooting tips if this appears to be a network source
                        if self.is_network_source:
                            self._show_network_troubleshooting_tips()
                        
                        return False
            except Exception as e:
                # Save progress for any unexpected exception (KeyboardInterrupt, MemoryError, etc.)
                self._save_progress_state(manifest, completed_files, failed_files)
                print(f"\nUpdate operation interrupted by unexpected error: {e}")
                print(f"Successfully copied: {len(completed_files)} files")
                print(f"Failed to copy: {len(failed_files)} files")
                print(f"Progress has been saved. Run the update command again to resume from where it left off.")
                
                # Show network troubleshooting tips if this appears to be a network source
                if self.is_network_source:
                    self._show_network_troubleshooting_tips()
                
                return False
                    
        print("\nUpdate operation completed successfully!")
        return True
        
    def verify(self) -> bool:
        """Verify that all files in destination match the manifest.
        
        Returns:
            True if all files verify correctly, False otherwise
        """
        manifest = self._load_manifest()
        if not manifest:
            return False
            
        print("Verifying archive integrity...")
        
        verified_count = 0
        error_count = 0
        missing_count = 0
        
        # Calculate total size for progress tracking
        total_size = sum(file_info['size'] for file_info in manifest['files'].values())
        progress_bar = self._create_progress_bar(
            manifest['files'].items(),
            "Verifying",
            "files",
            total_size
        )
        
        for rel_path, file_info in progress_bar:
            dest_path = self.destination_dir / rel_path
            
            if not dest_path.exists():
                tqdm.write(f"Missing: {rel_path}")
                missing_count += 1
                continue
                
            try:
                dest_hash = self._calculate_hash(dest_path)
                if dest_hash != file_info['hash']:
                    tqdm.write(f"Hash mismatch: {rel_path}")
                    error_count += 1
                else:
                    verified_count += 1
            except RuntimeError as e:
                tqdm.write(f"Error verifying {rel_path}: {e}")
                error_count += 1
                
        print(f"\nVerification complete:")
        print(f"Verified: {verified_count}")
        print(f"Errors: {error_count}")
        print(f"Missing: {missing_count}")
        
        return error_count == 0 and missing_count == 0
        
    def resume(self) -> bool:
        """Resume an interrupted copy or update operation.
        
        Returns:
            True if successful, False otherwise
        """
        print("Checking for interrupted operations...")
        progress_state = self._load_progress_state()
        
        if not progress_state:
            print("No interrupted operations found.")
            print("Use 'copy' or 'update' to start a new operation.")
            return True
            
        print(f"Found interrupted {progress_state['operation']} operation from {progress_state['timestamp']}")
        completed_files = progress_state.get('completed_files', [])
        failed_files = progress_state.get('failed_files', [])
        
        print(f"Previously completed: {len(completed_files)} files")
        print(f"Previously failed: {len(failed_files)} files")
        
        # Resume copy operation
        if progress_state['operation'] == 'copy':
            print("Resuming copy operation...")
            return self.copy(dry_run=False)
        else:
            print(f"Unknown operation type: {progress_state['operation']}")
            return False
            
    def status(self) -> bool:
        """Show status of the archive.
        
        Returns:
            True if successful, False otherwise
        """
        manifest = self._load_manifest()
        if not manifest:
            return False
            
        print(f"Archive Status")
        print(f"=" * 50)
        print(f"Source: {manifest['source_dir']}")
        print(f"Destination: {manifest['destination_dir']}")
        print(f"Created: {manifest['created']}")
        if 'last_updated' in manifest:
            print(f"Last updated: {manifest['last_updated']}")
        print(f"Total files: {manifest['total_files']:,}")
        print(f"Total size: {self._format_size(manifest['total_size'])}")
        
        # Quick check for missing files with progress bar
        print("\nChecking file presence...")
        missing_count = 0
        for rel_path in tqdm(manifest['files'], desc="Checking files", unit="files"):
            dest_path = self.destination_dir / rel_path
            if not dest_path.exists():
                missing_count += 1
                
        if missing_count > 0:
            print(f"Missing files: {missing_count}")
        else:
            print("All files present in destination")
            
        return True
        
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
        
    def _create_progress_bar(self, iterable, desc: str, unit: str = "items", 
                           total_size: Optional[int] = None) -> tqdm:
        """Create a customized progress bar with size information if available.
        
        Args:
            iterable: The iterable to wrap
            desc: Description for the progress bar
            unit: Unit name for progress
            total_size: Optional total size in bytes to show in progress
            
        Returns:
            tqdm progress bar instance
        """
        if total_size:
            size_desc = f"{desc} ({self._format_size(total_size)})"
        else:
            size_desc = desc
            
        return tqdm(iterable, 
                   desc=size_desc, 
                   unit=unit,
                   unit_scale=True,
                   dynamic_ncols=True,
                   ascii=True if not sys.stdout.isatty() else False)
