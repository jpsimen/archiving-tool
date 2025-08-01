#!/usr/bin/env python3
"""
Test script to demonstrate SMB reconnection functionality.
This script shows how to use the enhanced archiving tool with SMB sources.
"""

import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from archiving_tool.core import ArchivingTool

def test_smb_detection():
    """Test SMB detection and reconnection features."""
    
    # Example SMB paths for testing
    test_paths = [
        "/mnt/smb_share",  # Common SMB mount point
        "/media/network_drive",  # Another common mount point
        "//server/share",  # UNC path
        "/home/user/local_folder"  # Local path for comparison
    ]
    
    print("SMB Detection and Reconnection Test")
    print("=" * 50)
    
    for test_path in test_paths:
        print(f"\nTesting path: {test_path}")
        
        try:
            # Create archiving tool instance with test path as source
            tool = ArchivingTool(
                source_dir=test_path,
                destination_dir="/tmp/test_archive"
            )
            
            # Test network path detection
            if tool.is_network_source:
                print(f"✓ Detected as network source")
                
                # Test SMB mount detection (this will fail for non-existent paths)
                try:
                    if tool._is_smb_mount(Path(test_path)):
                        print(f"✓ Detected as SMB mount")
                        
                        # Test mount command generation
                        mount_cmd = tool._get_smb_mount_command(Path(test_path))
                        if mount_cmd:
                            print(f"✓ Generated mount command: {mount_cmd}")
                        else:
                            print("✗ Could not generate mount command")
                    else:
                        print(f"- Not an SMB mount (or not mounted)")
                except Exception as e:
                    print(f"- SMB detection failed: {e}")
            else:
                print(f"- Detected as local source")
                
        except Exception as e:
            print(f"✗ Error testing path: {e}")

def demonstrate_usage():
    """Show example usage of the new features."""
    
    print("\n" + "=" * 50)
    print("USAGE EXAMPLES")
    print("=" * 50)
    
    print("""
1. Basic usage with SMB source:
   tool = ArchivingTool("/mnt/smb_share", "/backup/destination")
   tool.init()  # Will detect SMB and enable enhanced retry logic
   tool.copy()  # Will automatically attempt reconnection on failures

2. Manual reconnection:
   if not tool._is_source_accessible():
       tool.reconnect_network_source()

3. Enhanced error handling:
   - Errno 57 (Socket is not connected) will trigger automatic SMB remount
   - Up to 8 retries with 5-second delays for network sources
   - Automatic troubleshooting tips when persistent failures occur

4. Error scenarios handled:
   - SMB server disconnection
   - Network timeouts
   - Mount point becoming inaccessible
   - Authentication token expiration
""")

if __name__ == "__main__":
    test_smb_detection()
    demonstrate_usage()
