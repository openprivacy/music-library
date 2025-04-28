#!/usr/bin/env python3

"""
showoftheday: Display shows from this date (in other years),
optionally add them to the current playlist and start playing.

If run as 'deadoftheday', restricts search to The_Grateful_Dead.
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime
from pathlib import Path

# Constants
COLUMN_WIDTHS = {'date': 12, 'artist': 40, 'album': 60}
DATABASE_SERVICE = "mariadb"
MUSIC_DB = "music"
MOUNTDIR_DEFAULT = "/cycles/flac"


def assert_database_running():
    """Ensure the database service is active."""
    result = subprocess.run(
        ['systemctl', 'is-active', DATABASE_SERVICE],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True
    )
    if result.stdout.strip() == 'inactive':
        subprocess.run(['sudo', 'systemctl', 'start', DATABASE_SERVICE])


def assert_mountdir_mounted(mountdir):
    """Ensure the mount directory is mounted (optional)."""
    result = subprocess.run(
        ['mountpoint', mountdir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    if result.returncode != 0:
        subprocess.run(['mount', mountdir])


def query_files(date, prefix):
    """Query the music database for files matching the given date and prefix."""
    like_pattern = f"%/{prefix}____-{date}%"
    query = f"SELECT filepath, artist, album FROM songs WHERE filepath LIKE '{like_pattern}' ORDER BY filepath ASC"

    try:
        result = subprocess.run(
            ['mysql', MUSIC_DB, '-B', '-N', '-e', query],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.strip().split('\n') if result.stdout else []
    except subprocess.CalledProcessError as e:
        print(f"Error querying database: {e.stderr.strip()}")
        sys.exit(1)


def enqueue_and_play(songs, queue=False, auto_play=False):
    """Handle Rhythmbox queue operations."""
    if queue:
        subprocess.run(['rhythmbox-client', '--clear-queue'])

    lastdir = ''
    count = 0
    print_header()
    for song in songs:
        (filepath, artist, album) = song.split('\t')
        thisdir = str(Path(filepath).parent)
        if thisdir != lastdir:
            lastdir = thisdir
            date_formatted = extract_date_from_filepath(filepath)
            print(
                format_field(date_formatted, COLUMN_WIDTHS['date']) +
                format_field(artist, COLUMN_WIDTHS['artist']) +
                format_field(album, COLUMN_WIDTHS['album'])
            )
            count += 1
        if queue:
            subprocess.run(['rhythmbox-client', '--enqueue', filepath])

    if auto_play:
        subprocess.run(['rhythmbox-client', '--play'])

    return count


def format_field(value, width):
    if len(value) > width:
        return value[:width-3] + '...'
    return value.ljust(width)


def extract_date_from_filepath(filepath):
    parts = filepath.split('/')
    for part in parts:
        if len(part) >= 10 and part[4] == '-' and part[7] == '-':
            return part[:10]
    return 'Unknown'


def print_header():
    headers = ['Date', 'Artist', 'Album']
    line = ''.join(format_field(header, COLUMN_WIDTHS[field.lower()]) for field, header in zip(COLUMN_WIDTHS.keys(), headers))
    print(line)
    print('-' * len(line))


def valid_date(date_str):
    """Validate date format mm-dd."""
    try:
        datetime.strptime(date_str, "%m-%d")
        return date_str
    except ValueError:
        raise argparse.ArgumentTypeError(f"Date '{date_str}' is not in 'mm-dd' format.")


def main():
    parser = argparse.ArgumentParser(description="Show concerts from today's date (in other years).")
    parser.add_argument('date', nargs='?', type=valid_date,
                        help="Date in mm-dd format. Defaults to today's date if omitted.")
    parser.add_argument('action', nargs='?', choices=['play'],
                        help="Optional action: 'play' to queue and play shows.")
    args = parser.parse_args()

    # Script name detection
    script_name = Path(sys.argv[0]).name
    prefix = 'The_Grateful_Dead/' if script_name == 'deadoftheday' else ''

    # Determine date
    date = args.date or datetime.now().strftime('%m-%d')

    # Determine actions
    queue = args.action == 'play'

    assert_database_running()
    # assert_mountdir_mounted(os.getenv('MOUNTDIR', MOUNTDIR_DEFAULT))  # Uncomment if needed

    songs = query_files(date, prefix)

    if not songs:
        print(f"No concerts found for {date}.")
        sys.exit(0)

    count = enqueue_and_play(songs, queue, auto_play=queue)

    print()
    print(f"{count} concerts played on this day in history ({date})!")


if __name__ == '__main__':
    main()
