#!/usr/bin/env python3

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mysql-connector-python",
#   "mutagen",
# ]
# ///

"""
musicdir_index.py – Server-side music library indexer
======================================================
Walks the FLAC root directory, discovers shows (Band/yyyy-mm-dd) and tracks
(##-Song_Name.flac), and upserts them into the MySQL ``music`` database.

Designed to run:
  • Once as a full initial import.
  • Nightly via cron for incremental updates (only changed/new files touched).

Usage
-----
    python musicdir_index.py [--root /imagine/flac] [--full]

    --root PATH   Override the FLAC root (default: /imagine/flac)
    --full        Force a full rescan even if files are unchanged
    --verbose     Log every file processed (default: only show/track changes)

Requirements
------------
    pip install mysql-connector-python

Environment variables (or a .env file loaded by the caller)
------------------------------------------------------------
    MUSIC_DB_HOST     MySQL host        (default: 127.0.0.1)
    MUSIC_DB_PORT     MySQL port        (default: 3306)
    MUSIC_DB_USER     MySQL user        (default: music)
    MUSIC_DB_PASSWORD MySQL password    (default: musicpass)
    MUSIC_DB_NAME     MySQL database    (default: music)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import mysql.connector
from mysql.connector import MySQLConnection
from mutagen.flac import FLAC

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_FLAC_ROOT = "/imagine/flac"

DB_CONFIG = {
    "host":     os.getenv("MUSIC_DB_HOST",     "127.0.0.1"),
    "port":     int(os.getenv("MUSIC_DB_PORT", "3306")),
    "user":     os.getenv("MUSIC_DB_USER",     "music"),
    "password": os.getenv("MUSIC_DB_PASSWORD", "musicpass"),
    "database": os.getenv("MUSIC_DB_NAME",     "music"),
    "charset":  "utf8mb4",
}

# Regex patterns for the expected directory/file layout.
_DATE_RE  = re.compile(r"^\d{4}-\d{2}-\d{2}\w*$")          # yyyy-mm-dd
# Extended prefix: yyyy-mm-dd[.]tNN[sep+title].flac  (e.g. Iggy_Pop, Kathleen_Edwards)
_TRACK_EXT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.?t(\d+)(?:[_\-.\s](.+))?\.flac$", re.IGNORECASE)
# Standard: NN[sep]Song_Name.flac
_TRACK_RE     = re.compile(r"^(\d+)[_\-.\s](.+)\.flac$", re.IGNORECASE)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def connect() -> MySQLConnection:
    """Return an open database connection."""
    return mysql.connector.connect(**DB_CONFIG)


def upsert_show(
    cursor,
    band: str,
    show_date: datetime,
    dir_path: str,
    file_count: int,
) -> int:
    """
    Insert or update a show row.

    Returns the show's primary key (id).
    """
    cursor.execute(
        """
        INSERT INTO shows (band, show_date, dir_path, file_count)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            band       = VALUES(band),
            show_date  = VALUES(show_date),
            file_count = VALUES(file_count),
            updated_at = CURRENT_TIMESTAMP
        """,
        (band, show_date.date(), dir_path, file_count),
    )
    if cursor.lastrowid:
        return cursor.lastrowid

    # Row already existed; fetch its id.
    cursor.execute("SELECT id FROM shows WHERE dir_path = %s", (dir_path,))
    row = cursor.fetchone()
    return row[0]


def upsert_track(
    cursor,
    show_id: int,
    file_path: str,
    track_num: int | None,
    title: str,
    file_mtime: datetime,
    album: str | None = None,
) -> None:
    """Insert or update a track row."""
    cursor.execute(
        """
        INSERT INTO tracks (show_id, file_path, track_num, title, album, file_mtime)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            track_num  = VALUES(track_num),
            title      = VALUES(title),
            album      = VALUES(album),
            file_mtime = VALUES(file_mtime),
            updated_at = CURRENT_TIMESTAMP
        """,
        (show_id, file_path, track_num, title, album, file_mtime),
    )


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def parse_track_filename(filename: str) -> tuple[int | None, str]:
    """
    Extract track number and human-readable title from a FLAC filename.

    Examples
    --------
    "01-Dark_Star.flac"                  →  (1, "Dark Star")
    "12 - Help On The Way.flac"          →  (12, "Help On The Way")
    "1991-07-12.t03.Lust_For_Life.flac"  →  (3, "Lust For Life")
    "2002-12-06t08.flac"                 →  (8, "2002-12-06t08")
    "Drums.flac"                         →  (None, "Drums")
    """
    m = _TRACK_EXT_RE.match(filename)
    if m:
        track_num = int(m.group(1))
        raw_title = m.group(2) or Path(filename).stem
    else:
        m = _TRACK_RE.match(filename)
        if m:
            track_num = int(m.group(1))
            raw_title = m.group(2)
        else:
            track_num = None
            raw_title = Path(filename).stem

    # Replace underscores and collapse whitespace.
    title = raw_title.replace("_", " ").strip()
    return track_num, title


def mtime_to_datetime(path: Path) -> datetime:
    """Return the file's mtime as a naive UTC datetime."""
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def extract_album(path: Path) -> str | None:
    """Read the album Vorbis comment from a FLAC file; returns None on failure."""
    try:
        audio = FLAC(str(path))
        values = audio.get("album") or audio.get("ALBUM")
        if values:
            return str(values[0]).strip() or None
        return None
    except Exception as exc:
        log.warning("Could not read metadata from %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Core scanning logic
# ---------------------------------------------------------------------------

def scan_library(
    flac_root: Path,
    conn: MySQLConnection,
    *,
    force_full: bool = False,
    verbose: bool = False,
) -> dict[str, int]:
    """
    Walk *flac_root* and upsert all discovered shows and tracks.

    Expected layout::

        <flac_root>/
          <Band_Name>/
            <yyyy-mm-dd>/
              ##-Song_Name.flac
              ...

    Returns a statistics dictionary with counts of shows and tracks
    inserted / updated / skipped.
    """
    stats = {"shows_upserted": 0, "tracks_upserted": 0, "tracks_skipped": 0}
    cursor = conn.cursor()

    # Build a cache of existing track mtimes to skip unchanged files quickly.
    track_mtime_cache: dict[str, datetime] = {}
    if not force_full:
        cursor.execute("SELECT file_path, file_mtime FROM tracks")
        for row in cursor.fetchall():
            track_mtime_cache[row[0]] = row[1]

    for band_dir in sorted(flac_root.iterdir()):
        if not band_dir.is_dir() or band_dir.name.startswith("."):
            continue

        band = band_dir.name.replace("_", " ")

        for date_dir in sorted(band_dir.iterdir()):
            if not date_dir.is_dir() or not _DATE_RE.match(date_dir.name):
                if verbose:
                    log.debug("Skipping non-date directory: %s", date_dir)
                continue

            try:
                show_date = datetime.strptime(date_dir.name[:10], "%Y-%m-%d")
            except ValueError:
                log.warning("Unexpected date format: %s – skipped", date_dir)
                continue

            # Collect FLAC files in this show directory.
            flac_files = sorted(
                f for f in date_dir.iterdir()
                if f.is_file() and f.suffix.lower() == ".flac"
            )

            dir_path = str(
                Path(band_dir.name) / date_dir.name
            )  # e.g. "Grateful_Dead/1977-05-08"

            # Pre-compute mtimes once; reused for the fast-path check and the
            # per-track upsert below.
            file_mtimes = {f: mtime_to_datetime(f) for f in flac_files}

            # Fast-path: if every track in this show is already cached with an
            # unchanged mtime, skip the whole show – no DB calls, no logging.
            if not force_full and flac_files:
                if all(
                    track_mtime_cache.get(
                        str(Path(band_dir.name) / date_dir.name / f.name)
                    ) == file_mtimes[f].replace(microsecond=0)
                    for f in flac_files
                ):
                    stats["tracks_skipped"] += len(flac_files)
                    continue

            show_id = upsert_show(
                cursor,
                band=band,
                show_date=show_date,
                dir_path=dir_path,
                file_count=len(flac_files),
            )
            stats["shows_upserted"] += 1
            log.debug("Show: %s  (%d tracks)", dir_path, len(flac_files))

            for flac_file in flac_files:
                rel_path = str(
                    Path(band_dir.name) / date_dir.name / flac_file.name
                )
                file_mtime = file_mtimes[flac_file]

                # Skip if file is unchanged since last index run.
                cached_mtime = track_mtime_cache.get(rel_path)
                if cached_mtime and not force_full:
                    # MySQL stores seconds; truncate microseconds for comparison.
                    if cached_mtime == file_mtime.replace(microsecond=0):
                        stats["tracks_skipped"] += 1
                        if verbose:
                            log.debug("Unchanged: %s", rel_path)
                        continue

                track_num, title = parse_track_filename(flac_file.name)
                album = extract_album(flac_file)
                upsert_track(
                    cursor,
                    show_id=show_id,
                    file_path=rel_path,
                    track_num=track_num,
                    title=title,
                    file_mtime=file_mtime,
                    album=album,
                )
                stats["tracks_upserted"] += 1
                log.info("Indexed: %s", rel_path)

        conn.commit()

    cursor.close()
    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index a FLAC music library into MySQL."
    )
    parser.add_argument(
        "--root",
        default=DEFAULT_FLAC_ROOT,
        help=f"Path to the FLAC root directory (default: {DEFAULT_FLAC_ROOT})",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Force a full rescan, ignoring cached mtimes",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Log every file processed",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    flac_root = Path(args.root)
    if not flac_root.is_dir():
        log.error("FLAC root not found: %s", flac_root)
        sys.exit(1)

    log.info("Connecting to MySQL at %s:%s …", DB_CONFIG["host"], DB_CONFIG["port"])
    try:
        conn = connect()
    except mysql.connector.Error as exc:
        log.error("Database connection failed: %s", exc)
        sys.exit(1)

    log.info("Scanning %s …", flac_root)
    try:
        stats = scan_library(
            flac_root,
            conn,
            force_full=args.full,
            verbose=args.verbose,
        )
    finally:
        conn.close()

    log.info(
        "Done. Shows upserted: %d  |  Tracks upserted: %d  |  Tracks skipped (unchanged): %d",
        stats["shows_upserted"],
        stats["tracks_upserted"],
        stats["tracks_skipped"],
    )


if __name__ == "__main__":
    main()
