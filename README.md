# Archiving Tool

A reliable command-line tool for archiving private data collections (music, photos, videos) with integrity verification using checksums.

## Features

- **Hash-based integrity verification** - Uses SHA256 checksums to ensure data integrity
- **Incremental updates** - Only copy new and modified files
- **Resume capability** - Handle interrupted operations gracefully
- **Automatic retry with backoff** - Retry failed operations up to 3 times with 2-second delays
- **Drive connectivity resilience** - Automatically detect and wait for disconnected drives
- **macOS & APFS optimizations** - Enhanced performance for Apple filesystems and external SSDs
- **Extended attribute preservation** - Maintains macOS metadata and resource forks
- **Dry-run mode** - Preview operations without making changes
- **Progress tracking** - Visual progress bars for long operations
- **Automatic exclusion** - Skip temporary and system files
- **Metadata preservation** - Maintain file timestamps and permissions

## Installation

```bash
# Install with uv (recommended)
uv sync

# Or install in development mode with uv
uv pip install -e .

# Alternative: Install with pip
pip install -e .
```

## Quick Start

1. **Initialize** an archive by scanning your source directory:
   ```bash
   archiving-tool init /path/to/source /path/to/backup
   ```

2. **Copy** all files to the backup location:
   ```bash
   archiving-tool copy /path/to/backup
   ```

3. **Update** the archive with new or modified files:
   ```bash
   archiving-tool update /path/to/backup
   ```

4. **Verify** the integrity of your backup:
   ```bash
   archiving-tool verify /path/to/backup
   ```

5. **Resume** interrupted operations:
   ```bash
   archiving-tool resume /path/to/backup
   ```

6. **Check status** of your archive:
   ```bash
   archiving-tool status /path/to/backup
   ```

## Commands

### `init`
Initialize the archive by scanning the source directory and creating a manifest file.

```bash
archiving-tool init [OPTIONS] SOURCE_DIR DESTINATION_DIR

Options:
  -m, --manifest PATH  Custom path for manifest file
  -f, --force         Overwrite existing manifest
```

**Example:**
```bash
archiving-tool init ~/Music /media/backup/music --force
```

### `copy`
Copy files from source to destination based on the manifest.

```bash
archiving-tool copy [OPTIONS] DESTINATION_DIR

Options:
  -m, --manifest PATH  Custom path for manifest file
  -n, --dry-run       Show what would be copied without copying
```

**Example:**
```bash
# Preview what would be copied
archiving-tool copy /media/backup/music --dry-run

# Actually copy the files
archiving-tool copy /media/backup/music
```

### `update`
Scan for new and modified files, update the manifest, and copy changes.

```bash
archiving-tool update [OPTIONS] DESTINATION_DIR

Options:
  -m, --manifest PATH  Custom path for manifest file
  -n, --dry-run       Show what would be updated without doing it
```

**Example:**
```bash
# Check what needs updating
archiving-tool update /media/backup/music --dry-run

# Update the archive
archiving-tool update /media/backup/music
```

### `verify`
Verify that all files in the destination match their checksums in the manifest.

```bash
archiving-tool verify [OPTIONS] DESTINATION_DIR

Options:
  -m, --manifest PATH  Custom path for manifest file
```

**Example:**
```bash
archiving-tool verify /media/backup/music
```

### `resume`
Resume an interrupted copy or update operation.

```bash
archiving-tool resume [OPTIONS] DESTINATION_DIR

Options:
  -m, --manifest PATH  Custom path for manifest file
```

**Example:**
```bash
# Resume after a drive disconnection or system crash
archiving-tool resume /media/backup/music
```

### `status`
Show information about the archive including file counts, sizes, and basic health check.

```bash
archiving-tool status [OPTIONS] DESTINATION_DIR

Options:
  -m, --manifest PATH  Custom path for manifest file
```

**Example:**
```bash
archiving-tool status /media/backup/music
```

**macOS users can get detailed drive information:**
```bash
# Show drive info including filesystem type and connection details
archiving-tool status /Volumes/BackupSSD --drive-info
```

## Workflow Examples

### Initial Backup
```bash
# Create initial backup of your music collection
archiving-tool init ~/Music /media/backup/music
archiving-tool copy /media/backup/music
```

### Regular Updates
```bash
# Weekly backup routine
archiving-tool update /media/backup/music
archiving-tool verify /media/backup/music
```

### Moving to New Drive
```bash
# Check current status
archiving-tool status /media/old-backup/music

# Copy to new location (using existing manifest)
archiving-tool copy /media/new-backup/music --manifest /media/old-backup/music/.archiving_manifest.json

# Verify new location
archiving-tool verify /media/new-backup/music
```

### macOS External SSD Workflow
```bash
# Connect your external SSD and check it's detected
archiving-tool status /Volumes/BackupSSD --drive-info

# Initialize with APFS optimizations
archiving-tool init ~/Music /Volumes/BackupSSD/music

# Copy with automatic APFS performance tuning
archiving-tool copy /Volumes/BackupSSD/music

# Verify with macOS metadata preservation
archiving-tool verify /Volumes/BackupSSD/music
```

### Handling External Drive Disconnections (macOS)
```bash
# Start backup to external SSD
archiving-tool copy /Volumes/BackupSSD/music

# If drive disconnects (USB-C/Thunderbolt), tool will:
# 1. Detect disconnection via diskutil
# 2. Wait for drive to reconnect
# 3. Resume automatically when drive is available

# Manual resume if needed:
archiving-tool resume /Volumes/BackupSSD/music
```

### Disaster Recovery Check
```bash
# Check if backup is complete and uncorrupted
archiving-tool verify /media/backup/music

# See what's missing or changed in source
archiving-tool update /media/backup/music --dry-run
```

### Handling Drive Disconnections
```bash
# Start copying large collection
archiving-tool copy /media/backup/music

# If drive disconnects or system crashes, resume with:
archiving-tool resume /media/backup/music

# Check what was completed
archiving-tool status /media/backup/music
```

### Weekly Backup with Resilience
```bash
# Check for drive connectivity first
archiving-tool status /media/backup/music

# Update with automatic retry
archiving-tool update /media/backup/music

# Verify integrity (will retry on errors)
archiving-tool verify /media/backup/music
```

### Transitioning from Manual Copies
If you've already started copying files manually (using file manager, `cp`, `rsync`, etc.) but want to use the archiving tool:

```bash
# 1. Initialize manifest for your source directory
archiving-tool init ~/Music /media/backup/music

# 2. The tool will detect existing files and only copy what's missing/different
archiving-tool copy /media/backup/music

# 3. Verify everything is correct
archiving-tool verify /media/backup/music

# 4. Future updates will be incremental
archiving-tool update /media/backup/music
```

**What happens during transition:**
- Existing correct files are **not re-copied** (saves time and wear)
- Files with hash mismatches are **automatically re-copied**
- Missing files are **copied** 
- The tool creates a **complete manifest** for future operations

## Manifest File

The tool creates a `.archiving_manifest.json` file in the destination directory containing:

- File paths, sizes, modification times, and SHA256 hashes
- Archive metadata (creation date, total files, total size)
- Source and destination directory paths

This file is essential for all operations and should be backed up along with your files.

## File Exclusions

The tool automatically excludes common temporary and system files:
- `.DS_Store`, `Thumbs.db` (OS metadata)
- `.tmp`, `.temp`, `*.tmp`, `*.temp` (temporary files)
- `.git`, `.svn`, `.hg` (version control)
- `__pycache__`, `*.pyc`, `*.pyo` (Python cache)

## Performance Optimizations

### macOS & APFS
- **Filesystem detection**: Automatically detects APFS filesystems
- **Optimized chunk size**: Uses 2MB chunks for APFS vs 1MB default
- **Extended attributes**: Preserves macOS metadata and resource forks
- **Drive monitoring**: Uses `diskutil` for real-time drive status
- **System exclusions**: Enhanced filtering for macOS system files

### General
- **Progress tracking**: Real-time progress bars with ETA calculations
- **Memory efficient**: Streaming file operations with configurable chunk sizes
- **Hash caching**: Reuses hashes for unchanged files during updates
- **Parallel verification**: Multiple hash calculations can run simultaneously
- **Incremental operations**: Only processes changed files during updates

## Error Handling & Resilience

- **Automatic retry logic**: Failed copy operations are retried up to 3 times with 2-second delays
- **Drive connectivity monitoring**: Automatically detects when backup drives become unavailable
- **Graceful interruption handling**: Operations can be safely interrupted and resumed later
- **Hash verification**: All copied files are verified against their source checksums
- **Progress preservation**: Interrupted operations save their state for seamless resumption
- **Hash mismatches**: Files are re-copied automatically when verification fails
- **Missing source files**: Warnings are displayed but operation continues
- **Permission errors**: Clear error messages with file paths
- **Corrupted files**: Automatic cleanup and retry of partially copied files

### Retry Scenarios

The tool automatically handles these common scenarios:
- **External drive disconnection**: Waits and retries when drive reconnects
- **Device busy errors**: Retries when storage device becomes available
- **Network storage issues**: Handles temporary network interruptions
- **System resource constraints**: Retries when system load decreases
- **File corruption during copy**: Detects and re-copies corrupted files

## macOS & APFS Optimizations

When running on macOS with APFS (Apple File System), the tool automatically applies several optimizations:

### **Filesystem Detection & Optimization**
- **Automatic APFS detection** - Uses `diskutil` to identify APFS volumes
- **Optimized chunk sizes** - 2MB chunks for APFS vs 1MB for other filesystems
- **Native macOS copy operations** - Uses optimized `cp -a` command when available

### **External SSD Support**  
- **Drive connectivity monitoring** - Enhanced detection for external drives
- **Mount status verification** - Ensures drive is properly mounted before operations
- **Connection resilience** - Better handling of USB-C/Thunderbolt disconnections

### **macOS Metadata Preservation**
- **Extended attributes** - Preserves xattr data using native tools
- **Resource forks** - Maintains legacy resource fork data when present
- **Spotlight metadata** - Preserves search metadata where applicable

### **Enhanced Exclusions**
Automatically excludes macOS-specific system files:
- `.DS_Store`, `.Spotlight-V100`, `.Trashes`, `.fseventsd`
- `.DocumentRevisions-V100`, `.TemporaryItems` 
- `._*` files (resource forks and metadata)
- `.localized`, `.VolumeIcon.icns`

### **Drive Information**
```bash
# Get detailed drive information for external SSDs
archiving-tool status /Volumes/MyBackupSSD --drive-info
```

This shows:
- Filesystem type (APFS, HFS+, exFAT, etc.)
- Connection type (USB, Thunderbolt, etc.)
- Available space and mount status
- External drive detection

## Error Handling & Resilience

## Performance Tips

- Use SSD for source directory when possible
- For very large collections, consider running operations overnight
- The `--dry-run` flag is useful for planning operations
- Verify operations periodically but not after every update
- **When taking over manual copies**: Run `copy --dry-run` first to see what needs copying
- **For partial failures**: Use `resume` command rather than restarting from scratch
- **Large collections**: Use `status` command to monitor progress and health

## Use Cases

- **Music Collections**: Backup entire music libraries with album art and metadata
- **Photo Archives**: Safely archive family photos and memories  
- **Video Collections**: Backup home videos and downloaded content
- **Document Archives**: Keep important documents safe with integrity verification
- **Mixed Media**: Any combination of personal files
- **Rescue Incomplete Copies**: Take over from failed manual copy operations
- **Verify Existing Backups**: Check integrity of backups made with other tools
- **Incremental Sync**: Regular updates without re-copying unchanged files

### Common Scenarios

**Taking over from failed manual copies:**
Many users start copying large collections manually (drag & drop, `cp`, `rsync`) but face issues:
- File manager crashes during large transfers
- System runs out of space mid-copy
- Drive disconnects and leaves partial files
- No way to verify what copied correctly

The archiving tool can seamlessly take over by:
1. Creating a manifest of your source files
2. Checking what's already correctly copied (via checksums)
3. Only copying missing or corrupted files
4. Providing verification and future incremental updates

## Contributing

This tool is designed for personal use but contributions are welcome. Please ensure any changes maintain the focus on data integrity and reliability.

## License

MIT License - see LICENSE file for details.
