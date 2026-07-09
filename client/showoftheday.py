#!/usr/bin/env python3

# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mysql-connector-python",
# ]
# ///

"""
showoftheday.py – macOS CLI for the remote music library
=========================================================
Queries the MySQL database on the XUbuntu server and either:

  • Lists all shows from a given MM-DD (any year) – the "show of the day" mode.
  • Lists all shows/tracks updated within the last N days.

The selected show or tracks are written as an M3U playlist that any
Mac music player (Swinsian, IINA, VLC …) can open directly.

Usage examples
--------------
    # Shows from June 13 in any year, pick interactively:
    python showoftheday.py --date 06-13

    # Shows added/changed in the last 7 days:
    python showoftheday.py --recent 7

    # Print M3U to stdout instead of opening a player:
    python showoftheday.py --date 06-13 --print

    # Specify the Samba mount point (default: /Volumes/imagine):
    python showoftheday.py --date 06-13 --mount /Volumes/imagine

Requirements
------------
    pip install mysql-connector-python

Environment variables (or export before running)
------------------------------------------------
    MUSIC_DB_HOST      Server IP/hostname   (default: 127.0.0.1)
    MUSIC_DB_PORT      MySQL port           (default: 3306)
    MUSIC_DB_USER                           (default: music)
    MUSIC_DB_PASSWORD                       (default: musicpass)
    MUSIC_DB_NAME                           (default: music)
    MUSIC_MOUNT        Samba mount point    (default: /Volumes/Flac)
    MUSIC_PLAYER       App to open M3U with (default: /Applications/Swinsian.app)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import NamedTuple

import mysql.connector

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host":     os.getenv("MUSIC_DB_HOST",     "127.0.0.1"),
    "port":     int(os.getenv("MUSIC_DB_PORT", "3306")),
    "user":     os.getenv("MUSIC_DB_USER",     "music"),
    "password": os.getenv("MUSIC_DB_PASSWORD", "musicpass"),
    "database": os.getenv("MUSIC_DB_NAME",     "music"),
    "charset":  "utf8mb4",
}

DEFAULT_MOUNT  = os.getenv("MUSIC_MOUNT",  "/Volumes/Flac")
DEFAULT_PLAYER = os.getenv("MUSIC_PLAYER", "/Applications/Swinsian.app")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Show(NamedTuple):
    show_id: int
    band: str
    show_date: str     # "yyyy-mm-dd"
    dir_path: str      # relative: "Band/yyyy-mm-dd"
    file_count: int
    album: str         # from first track's metadata (empty string if unset)


class Track(NamedTuple):
    track_id: int
    track_num: int | None
    title: str
    file_path: str     # relative: "Band/yyyy-mm-dd/##-Song.flac"


# ---------------------------------------------------------------------------
# Band filter helpers
# ---------------------------------------------------------------------------

DEAD_FILE = Path(__file__).parent / "dead.txt"
DEAD_DEFAULT = ["The Grateful Dead"]


def load_dead_bands() -> list[str]:
    """
    Read band names from dead.txt (one per line, underscores allowed).
    Returns names with underscores replaced by spaces to match the DB.
    Falls back to DEAD_DEFAULT if the file does not exist.
    """
    if DEAD_FILE.exists():
        names = [ln.strip() for ln in DEAD_FILE.read_text().splitlines() if ln.strip()]
        return [n.replace("_", " ") for n in names]
    return list(DEAD_DEFAULT)


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def connect() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(**DB_CONFIG)


def shows_by_month_day(cursor, month_day: str, bands: list[str] | None = None) -> list[Show]:
    """
    Return all shows whose date matches MM-DD (any year), sorted by date then band.

    *month_day* must be in the format ``MM-DD`` (e.g. ``"06-13"``).
    If *bands* is provided, only shows from those bands are returned.
    """
    month, day = month_day.split("-")
    band_filter = ""
    params: tuple = (int(month), int(day))
    if bands:
        placeholders = ", ".join(["%s"] * len(bands))
        band_filter = f"AND band IN ({placeholders})"
        params = (int(month), int(day), *bands)
    cursor.execute(
        f"""
        SELECT s.id, s.band, CAST(s.show_date AS CHAR), s.dir_path, s.file_count,
               COALESCE(MIN(t.album), '') AS album
        FROM shows s
        LEFT JOIN tracks t ON t.show_id = s.id AND t.album IS NOT NULL
        WHERE MONTH(s.show_date) = %s
          AND DAY(s.show_date)   = %s
          {band_filter}
        GROUP BY s.id, s.band, s.show_date, s.dir_path, s.file_count
        ORDER BY s.show_date, s.band
        """,
        params,
    )
    return [Show(*row) for row in cursor.fetchall()]


def shows_updated_recently(cursor, days: int, bands: list[str] | None = None) -> list[Show]:
    """
    Return shows that have had tracks added or changed in the last *days* days.
    If *bands* is provided, only shows from those bands are returned.
    """
    band_filter = ""
    params: tuple = (days,)
    if bands:
        placeholders = ", ".join(["%s"] * len(bands))
        band_filter = f"AND s.band IN ({placeholders})"
        params = (days, *bands)
    cursor.execute(
        f"""
        SELECT s.id, s.band,
               CAST(s.show_date AS CHAR),
               s.dir_path, s.file_count,
               COALESCE(MIN(ta.album), '') AS album
        FROM shows s
        JOIN tracks t  ON t.show_id = s.id
        LEFT JOIN tracks ta ON ta.show_id = s.id AND ta.album IS NOT NULL
        WHERE t.file_mtime >= NOW() - INTERVAL %s DAY
          {band_filter}
        GROUP BY s.id, s.band, s.show_date, s.dir_path, s.file_count
        ORDER BY MAX(t.file_mtime) DESC, s.band
        """,
        params,
    )
    return [Show(*row) for row in cursor.fetchall()]


def tracks_for_show(cursor, show_id: int) -> list[Track]:
    """Return all tracks for a show, ordered by track number then title."""
    cursor.execute(
        """
        SELECT id, track_num, title, file_path
        FROM tracks
        WHERE show_id = %s
        ORDER BY track_num, title
        """,
        (show_id,),
    )
    return [Track(*row) for row in cursor.fetchall()]


def tracks_updated_recently(cursor, days: int, bands: list[str] | None = None) -> list[Track]:
    """Return all tracks updated in the last *days* days, newest first."""
    band_filter = ""
    params: tuple = (days,)
    if bands:
        placeholders = ", ".join(["%s"] * len(bands))
        band_filter = f"AND s.band IN ({placeholders})"
        params = (days, *bands)
    cursor.execute(
        f"""
        SELECT t.id, t.track_num, t.title, t.file_path
        FROM tracks t
        JOIN shows s ON s.id = t.show_id
        WHERE t.file_mtime >= NOW() - INTERVAL %s DAY
          {band_filter}
        ORDER BY t.file_mtime DESC, t.file_path
        """,
        params,
    )
    return [Track(*row) for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------

def choose_show(shows: list[Show]) -> Show | None:
    """
    Display a numbered list of shows; prompt the user to choose one.

    Returns the chosen Show, or None if the user cancels.
    """
    if not shows:
        print("No shows found.")
        return None

    print()

    print(f"{'#':>4}  {'Date':<12}  {'Band':<35}  {'Tracks':>6}  Venue")
    print("-" * 80)
    for i, show in enumerate(shows, start=1):
        album = show.album
        if len(album) > 10 and album[4] == "-" and album[7] == "-" and album[10] == " ":
            album = album[11:]
        if len(album) > 80:
            album = album[:79] + "\u2026"
        print(f"{i:>4}  {show.show_date:<12}  {show.band:<35}  {show.file_count:>6}  {album}")
    print()

    while True:
        raw = input("Enter show number (or 'a' for all, 'q' to quit): ").strip()
        if raw.lower() == "q":
            return None
        if raw.lower() == "a":
            # Sentinel: the caller checks for None band.
            return Show(-1, "", "", "", 0)
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(shows):
                return shows[idx]
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(shows)}.")


def choose_tracks(tracks: list[Track], show: Show) -> list[Track]:
    """
    Optionally let the user narrow down to individual tracks.

    Returns the selected track list (may be the full list).
    """
    if not tracks:
        print("No tracks found for this show.")
        return []

    print()
    print(f"  Show: {show.band}  –  {show.show_date}")
    print()
    print(f"  {'#':>4}  {'Trk':>4}  Title")
    print("  " + "-" * 60)
    for i, t in enumerate(tracks, start=1):
        num_str = str(t.track_num) if t.track_num is not None else "  "
        print(f"  {i:>4}  {num_str:>4}  {t.title}")
    print()

    raw = input(
        "  Play all tracks (Enter), or enter track numbers (e.g. 1,3-5): "
    ).strip()

    if not raw:
        return tracks

    return _parse_track_selection(raw, tracks)


def _parse_track_selection(raw: str, tracks: list[Track]) -> list[Track]:
    """
    Parse a selection string like ``"1,3-5,7"`` into a list of Track objects.
    Invalid indices are ignored.
    """
    selected: list[Track] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start_s, end_s = part.split("-", 1)
                start, end = int(start_s) - 1, int(end_s) - 1
                selected.extend(tracks[start : end + 1])
            except (ValueError, IndexError):
                pass
        else:
            try:
                idx = int(part) - 1
                selected.append(tracks[idx])
            except (ValueError, IndexError):
                pass
    return selected


# ---------------------------------------------------------------------------
# M3U generation
# ---------------------------------------------------------------------------

MUSIC_PLAYLIST_NAME = "FlacLibraryList"


def build_m3u(tracks: list[Track], mount: str) -> str:
    """Build an M3U playlist string.

    Paths are constructed as ``<mount>/<relative_file_path>``.
    """
    base = Path(mount)
    lines = ["#EXTM3U"]
    for t in tracks:
        lines.append(f"#EXTINF:-1,{t.title}")
        lines.append(str(base / t.file_path))
    return "\n".join(lines) + "\n"


def write_m3u_temp(content: str) -> Path:
    """Write M3U content to a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".m3u", prefix="showoftheday_")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(content)
    return Path(path)


def open_in_player(m3u_path: Path, player: str) -> None:
    """Open the M3U file with the specified macOS application.

    For VLC, calls the bundle binary directly with ``--no-playlist-enqueue``
    so the current playlist is replaced rather than appended to.
    For all other players, falls back to ``open -a``.
    """
    player_path = Path(player)
    if player_path.stem.lower() == "vlc":
        bin_path = player_path / "Contents" / "MacOS" / "VLC"
        if bin_path.exists():
            # Stop any running VLC so the new playlist replaces it cleanly.
            subprocess.run(["pkill", "-x", "VLC"],
                           capture_output=True, check=False)
            time.sleep(0.3)
            subprocess.Popen(
                [str(bin_path), str(m3u_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
    subprocess.run(["open", "-a", player, str(m3u_path)], check=False)


def load_into_music_app(tracks: list[Track], mount: str, save: bool) -> None:
    """Load *tracks* into Music.app under ``MUSIC_PLAYLIST_NAME``.

    Writes a named ``.m3u`` file and opens it with Music.app.  The
    file-import handler (Launch Services) creates a playlist whose name
    matches the file stem, bypassing the Apple Events sandbox issues
    that prevent programmatic ``add``/``duplicate`` from working.

    When *save* is False the existing playlist is deleted first so the
    import produces a clean replacement.
    """
    if not save:
        del_script = "\n".join([
            'tell application "Music"',
            f'    if (exists user playlist "{MUSIC_PLAYLIST_NAME}") then',
            f'        delete user playlist "{MUSIC_PLAYLIST_NAME}"',
            "    end if",
            "end tell",
        ])
        subprocess.run(
            ["osascript", "-e", del_script],
            capture_output=True,
            check=False,
        )

    # The filename stem becomes the playlist name when Music.app imports it.
    m3u_path = Path(tempfile.gettempdir()) / f"{MUSIC_PLAYLIST_NAME}.m3u"
    m3u_path.write_text(build_m3u(tracks, mount), encoding="utf-8")

    subprocess.run(
        ["open", "-a", "/System/Applications/Music.app", str(m3u_path)],
        check=False,
    )


# ---------------------------------------------------------------------------
# Mode: by date
# ---------------------------------------------------------------------------

def run_date_mode(
    cursor,
    month_day: str,
    mount: str,
    player: str,
    print_only: bool,
    save: bool,
    bands: list[str] | None = None,
) -> None:
    """Interactive show-of-the-day flow."""
    shows = shows_by_month_day(cursor, month_day, bands)
    if not shows:
        print(f"No shows found for {month_day}.")
        return

    chosen = choose_show(shows)
    if chosen is None:
        return

    if chosen.show_id == -1:
        # User chose "all" – collect every track from every show.
        all_tracks: list[Track] = []
        for show in shows:
            all_tracks.extend(tracks_for_show(cursor, show.show_id))
        selected_tracks = all_tracks
    else:
        all_tracks_for_show = tracks_for_show(cursor, chosen.show_id)
        selected_tracks = choose_tracks(all_tracks_for_show, chosen)

    _output(selected_tracks, mount, player, print_only, save)


# ---------------------------------------------------------------------------
# Mode: recently updated
# ---------------------------------------------------------------------------

def run_recent_mode(
    cursor,
    days: int,
    mount: str,
    player: str,
    print_only: bool,
    all_tracks: bool,
    save: bool,
    bands: list[str] | None = None,
) -> None:
    """List recently added/changed content."""
    if all_tracks:
        tracks = tracks_updated_recently(cursor, days, bands)
        if not tracks:
            print(f"No tracks updated in the last {days} day(s).")
            return
        print(f"\nFound {len(tracks)} track(s) updated in the last {days} day(s).")
    else:
        shows = shows_updated_recently(cursor, days, bands)
        if not shows:
            print(f"No shows updated in the last {days} day(s).")
            return
        chosen = choose_show(shows)
        if chosen is None:
            return
        if chosen.show_id == -1:
            tracks = []
            for show in shows:
                tracks.extend(tracks_for_show(cursor, show.show_id))
        else:
            tracks = tracks_for_show(cursor, chosen.show_id)

    _output(tracks, mount, player, print_only, save)


# ---------------------------------------------------------------------------
# Shared output helper
# ---------------------------------------------------------------------------

def _output(
    tracks: list[Track],
    mount: str,
    player: str,
    print_only: bool,
    save: bool,
) -> None:
    if not tracks:
        print("No tracks selected.")
        return

    if print_only:
        print(build_m3u(tracks, mount))
        return

    print(f"\nOpening with: {player}\n")
    player_stem = Path(player).stem.lower()
    if player_stem == "music":
        print(f'Loading {len(tracks)} track(s) into "{MUSIC_PLAYLIST_NAME}" \u2026')
        load_into_music_app(tracks, mount, save)
    else:
        m3u_path = write_m3u_temp(build_m3u(tracks, mount))
        print(f"Playlist written to: {m3u_path}")
        open_in_player(m3u_path, player)


# ---------------------------------------------------------------------------
# Argument parsing & entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query the music library database and build a playlist."
    )

    mode = parser.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--date",
        metavar="MM-DD",
        help="Show all concerts recorded on this month/day (any year); defaults to today's MM-DD",
    )
    mode.add_argument(
        "--recent",
        metavar="DAYS",
        type=int,
        help="Show all content added/updated in the last DAYS days",
    )

    parser.add_argument(
        "--mount",
        default=DEFAULT_MOUNT,
        help=f"Samba mount point on this Mac (default: {DEFAULT_MOUNT})",
    )
    parser.add_argument(
        "--player",
        default=DEFAULT_PLAYER,
        help=f"macOS app to open the M3U with (default: {DEFAULT_PLAYER})",
    )
    parser.add_argument(
        "--print",
        dest="print_only",
        action="store_true",
        help="Print the M3U to stdout instead of opening a player",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Append to the player's existing playlist instead of clearing it first",
    )
    parser.add_argument(
        "--dead",
        action="store_true",
        help="Filter to bands listed in dead.txt (default: Grateful Dead)",
    )
    parser.add_argument(
        "--all",
        dest="all_tracks",
        action="store_true",
        help="(--recent only) List every updated track individually instead of grouping by show",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Default to today's MM-DD if neither --date nor --recent was given.
    if args.date is None and args.recent is None:
        args.date = date.today().strftime("%m-%d")

    bands = load_dead_bands() if args.dead else None

    try:
        conn = connect()
    except mysql.connector.Error as exc:
        print(f"ERROR: Could not connect to database: {exc}", file=sys.stderr)
        sys.exit(1)

    cursor = conn.cursor()
    try:
        if args.date:
            run_date_mode(
                cursor,
                month_day=args.date,
                mount=args.mount,
                player=args.player,
                print_only=args.print_only,
                save=args.save,
                bands=bands,
            )
        else:
            run_recent_mode(
                cursor,
                days=args.recent,
                mount=args.mount,
                player=args.player,
                print_only=args.print_only,
                all_tracks=args.all_tracks,
                save=args.save,
                bands=bands,
            )
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
