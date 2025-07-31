"""Archiving Tool - A reliable command-line tool for archiving private data collections."""

from .cli import cli
from .core import ArchivingTool

__version__ = "0.1.0"
__all__ = ["ArchivingTool", "cli"]


def main():
    """Main entry point for the CLI."""
    cli()
