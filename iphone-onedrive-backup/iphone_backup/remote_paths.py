"""Pure helpers for building OneDrive destination paths and upload chunks.

Kept dependency-free and side-effect-free so they can be unit-tested on any
platform (no Mac / iPhone / network needed).
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote


def sanitize_segment(name: str) -> str:
    """Make a single path segment safe for OneDrive.

    OneDrive disallows these characters in names: " * : < > ? / \\ |
    and names may not end with a space or period.
    """
    bad = '"*:<>?/\\|'
    cleaned = "".join("_" if c in bad else c for c in name)
    cleaned = cleaned.rstrip(" .")
    return cleaned or "_"


def remote_relative_path(
    source_relpath: str,
    captured: datetime,
    organize_by: str,
) -> str:
    """Return the path *below* the base folder for a given source file.

    source_relpath: path of the file relative to the DCIM (or source) root,
                    e.g. "100APPLE/IMG_0001.HEIC".
    captured:       best-known capture timestamp (used by "date" layout).
    organize_by:    "date" | "dcim" | "flat".
    """
    filename = sanitize_segment(source_relpath.replace("\\", "/").split("/")[-1])

    if organize_by == "flat":
        return filename

    if organize_by == "dcim":
        parts = [sanitize_segment(p) for p in source_relpath.replace("\\", "/").split("/") if p]
        return "/".join(parts) if parts else filename

    # default: organize by capture date
    year = f"{captured.year:04d}"
    month = f"{captured.month:02d}"
    return f"{year}/{month}/{filename}"


def full_remote_path(base_folder: str, relative: str) -> str:
    """Join the base folder and a relative path into one OneDrive path."""
    base = "/".join(sanitize_segment(p) for p in base_folder.split("/") if p)
    rel = "/".join(p for p in relative.split("/") if p)
    return f"{base}/{rel}" if base else rel


def encode_graph_path(remote_path: str) -> str:
    """Percent-encode a OneDrive path for use in a Graph `root:/{path}:` address.

    Slashes are preserved as separators; everything else is encoded.
    """
    return quote(remote_path, safe="/")


def chunk_ranges(total_size: int, chunk_size: int):
    """Yield (start, end_inclusive, length) tuples covering [0, total_size).

    Used for resumable OneDrive upload sessions, where each PUT carries a
    Content-Range header of `bytes {start}-{end}/{total}`.
    """
    if total_size <= 0:
        return
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    start = 0
    while start < total_size:
        end = min(start + chunk_size, total_size) - 1
        yield start, end, end - start + 1
        start = end + 1
