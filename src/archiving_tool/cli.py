"""Command line interface for the archiving tool."""

import sys
from pathlib import Path

import click
from colorama import Fore, Style, init

from .core import ArchivingTool

# Initialize colorama for cross-platform colored output
init(autoreset=True)


def print_success(message: str):
    """Print success message in green."""
    click.echo(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_error(message: str):
    """Print error message in red."""
    click.echo(f"{Fore.RED}✗ {message}{Style.RESET_ALL}")


def print_warning(message: str):
    """Print warning message in yellow."""
    click.echo(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Print info message in blue."""
    click.echo(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")


@click.group()
@click.version_option()
def cli():
    """A reliable command-line tool for archiving private data collections.
    
    This tool helps you safely copy and maintain collections of music, photos,
    videos, and other personal files with integrity verification using checksums.
    
    NETWORK SOURCES:
    Supports SMB/CIFS, NFS and other network sources with enhanced error handling:
    - Automatic detection of network paths (/mnt/, //server/share, etc.)
    - Active SMB reconnection when network disconnects
    - Enhanced retry logic with longer timeouts for network sources
    - Progress preservation and resume capability after network failures
    
    FEATURES:
    - SHA256 checksums for integrity verification
    - Progress tracking and resume capability
    - Intelligent retry logic with exponential backoff
    - Cross-platform support (Linux, macOS, Windows)
    """
    pass


@cli.command()
@click.argument('source_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.argument('destination_dir', type=click.Path(file_okay=False, dir_okay=True))
@click.option('--manifest', '-m', type=click.Path(), 
              help='Custom path for manifest file (default: <destination>/.archiving_manifest.json)')
@click.option('--force', '-f', is_flag=True, 
              help='Overwrite existing manifest')
def init(source_dir: str, destination_dir: str, manifest: str, force: bool):
    """Initialize the archive by scanning source directory and creating a manifest.
    
    SOURCE_DIR: Directory containing files to archive
    DESTINATION_DIR: Directory where files will be copied
    """
    print_info(f"Initializing archive...")
    
    try:
        tool = ArchivingTool(source_dir, destination_dir, manifest)
        if tool.init(force=force):
            print_success("Archive initialized successfully!")
        else:
            print_error("Failed to initialize archive")
            sys.exit(1)
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('destination_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--manifest', '-m', type=click.Path(), 
              help='Custom path for manifest file (default: <destination>/.archiving_manifest.json)')
@click.option('--dry-run', '-n', is_flag=True, 
              help='Show what would be copied without actually copying')
def copy(destination_dir: str, manifest: str, dry_run: bool):
    """Copy files from source to destination based on the manifest.
    
    DESTINATION_DIR: Directory where the manifest and files are located
    """
    if dry_run:
        print_info("Dry run mode - no files will be copied")
    else:
        print_info("Starting copy operation...")
    
    try:
        # We need to get source_dir from the manifest
        manifest_path = Path(manifest) if manifest else Path(destination_dir) / ".archiving_manifest.json"
        if not manifest_path.exists():
            print_error(f"Manifest file not found: {manifest_path}")
            print_info("Run 'archiving-tool init' first to create the manifest")
            sys.exit(1)
            
        import json
        with open(manifest_path, 'r') as f:
            manifest_data = json.load(f)
            
        source_dir = manifest_data['source_dir']
        
        tool = ArchivingTool(source_dir, destination_dir, manifest)
        if tool.copy(dry_run=dry_run):
            if not dry_run:
                print_success("Copy operation completed successfully!")
        else:
            print_error("Copy operation failed")
            sys.exit(1)
    except Exception as e:
        print_error(f"Copy operation failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('destination_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--manifest', '-m', type=click.Path(), 
              help='Custom path for manifest file (default: <destination>/.archiving_manifest.json)')
@click.option('--dry-run', '-n', is_flag=True, 
              help='Show what would be updated without actually doing it')
def update(destination_dir: str, manifest: str, dry_run: bool):
    """Update the manifest with new and modified files, then copy them.
    
    DESTINATION_DIR: Directory where the manifest and files are located
    """
    if dry_run:
        print_info("Dry run mode - no files will be copied")
    else:
        print_info("Starting update operation...")
    
    try:
        # Get source_dir from the manifest
        manifest_path = Path(manifest) if manifest else Path(destination_dir) / ".archiving_manifest.json"
        if not manifest_path.exists():
            print_error(f"Manifest file not found: {manifest_path}")
            print_info("Run 'archiving-tool init' first to create the manifest")
            sys.exit(1)
            
        import json
        with open(manifest_path, 'r') as f:
            manifest_data = json.load(f)
            
        source_dir = manifest_data['source_dir']
        
        tool = ArchivingTool(source_dir, destination_dir, manifest)
        if tool.update(dry_run=dry_run):
            if not dry_run:
                print_success("Update operation completed successfully!")
        else:
            print_error("Update operation failed")
            sys.exit(1)
    except Exception as e:
        print_error(f"Update operation failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('destination_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--manifest', '-m', type=click.Path(), 
              help='Custom path for manifest file (default: <destination>/.archiving_manifest.json)')
def verify(destination_dir: str, manifest: str):
    """Verify that all files in destination match their checksums.
    
    DESTINATION_DIR: Directory where the manifest and files are located
    """
    print_info("Starting verification...")
    
    try:
        # Get source_dir from the manifest
        manifest_path = Path(manifest) if manifest else Path(destination_dir) / ".archiving_manifest.json"
        if not manifest_path.exists():
            print_error(f"Manifest file not found: {manifest_path}")
            print_info("Run 'archiving-tool init' first to create the manifest")
            sys.exit(1)
            
        import json
        with open(manifest_path, 'r') as f:
            manifest_data = json.load(f)
            
        source_dir = manifest_data['source_dir']
        
        tool = ArchivingTool(source_dir, destination_dir, manifest)
        if tool.verify():
            print_success("All files verified successfully!")
        else:
            print_error("Verification failed - some files are corrupted or missing")
            sys.exit(1)
    except Exception as e:
        print_error(f"Verification failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('destination_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--manifest', '-m', type=click.Path(), 
              help='Custom path for manifest file (default: <destination>/.archiving_manifest.json)')
def resume(destination_dir: str, manifest: str):
    """Resume an interrupted copy or update operation.
    
    DESTINATION_DIR: Directory where the manifest and files are located
    """
    print_info("Checking for interrupted operations to resume...")
    
    try:
        # Get source_dir from the manifest
        manifest_path = Path(manifest) if manifest else Path(destination_dir) / ".archiving_manifest.json"
        if not manifest_path.exists():
            print_error(f"Manifest file not found: {manifest_path}")
            print_info("Run 'archiving-tool init' first to create the manifest")
            sys.exit(1)
            
        import json
        with open(manifest_path, 'r') as f:
            manifest_data = json.load(f)
            
        source_dir = manifest_data['source_dir']
        
        # Check for progress file
        progress_file = Path(destination_dir) / ".archiving_tool_progress.json"
        if not progress_file.exists():
            print_info("No interrupted operations found")
            print_info("Use 'copy' or 'update' commands to start new operations")
            return
            
        tool = ArchivingTool(source_dir, destination_dir, manifest)
        
        # Use the copy method which will automatically detect and resume from progress
        if tool.copy(dry_run=False):
            print_success("Resume operation completed successfully!")
        else:
            print_error("Resume operation failed")
            sys.exit(1)
    except Exception as e:
        print_error(f"Resume operation failed: {e}")
        sys.exit(1)


@cli.command()
@click.argument('destination_dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('--manifest', '-m', type=click.Path(), 
              help='Custom path for manifest file (default: <destination>/.archiving_manifest.json)')
@click.option('--drive-info', is_flag=True,
              help='Show detailed drive information (macOS only)')
def status(destination_dir: str, manifest: str, drive_info: bool):
    """Show status and information about the archive.
    
    DESTINATION_DIR: Directory where the manifest and files are located
    """
    try:
        # Get source_dir from the manifest
        manifest_path = Path(manifest) if manifest else Path(destination_dir) / ".archiving_manifest.json"
        if not manifest_path.exists():
            print_error(f"Manifest file not found: {manifest_path}")
            print_info("Run 'archiving-tool init' first to create the manifest")
            sys.exit(1)
            
        import json
        with open(manifest_path, 'r') as f:
            manifest_data = json.load(f)
            
        source_dir = manifest_data['source_dir']
        
        tool = ArchivingTool(source_dir, destination_dir, manifest)
        
        # Show drive info for macOS if requested
        if drive_info and tool.is_macos:
            _show_macos_drive_info(destination_dir)
            
        if not tool.status():
            print_error("Failed to get status")
            sys.exit(1)
    except Exception as e:
        print_error(f"Status check failed: {e}")
        sys.exit(1)


def _show_macos_drive_info(destination_dir: str):
    """Show macOS-specific drive information."""
    try:
        import subprocess
        print(f"\n{Fore.CYAN}macOS Drive Information:{Style.RESET_ALL}")
        print(f"=" * 50)
        
        result = subprocess.run(
            ['diskutil', 'info', destination_dir], 
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.split('\n')
            relevant_info = []
            for line in lines:
                if any(keyword in line for keyword in ['File System', 'Device Node', 'Volume Name', 'Mount Point', 'Total Size', 'Available Space', 'Connection']):
                    relevant_info.append(line.strip())
            
            for info in relevant_info:
                if info:
                    print(f"  {info}")
        else:
            print("  Could not retrieve drive information")
            
        # Check if it's an external drive
        result2 = subprocess.run(
            ['diskutil', 'list', 'external'], 
            capture_output=True, text=True, timeout=10
        )
        
        if result2.returncode == 0 and destination_dir in result2.stdout:
            print(f"  {Fore.GREEN}✓ External drive detected{Style.RESET_ALL}")
        
    except Exception as e:
        print(f"  Warning: Could not retrieve drive info: {e}")


if __name__ == '__main__':
    cli()
