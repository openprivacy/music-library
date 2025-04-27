import os
import sys
import logging
import argparse
import mysql.connector
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.oggvorbis import OggVorbis
from mutagen.id3 import ID3NoHeaderError

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')


def connect_db(host, user, password, database):
    """Connect to the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4'
        )
        return conn
    except mysql.connector.Error as err:
        logging.error(f"Database connection failed: {err}")
        sys.exit(1)


def find_audio_files(root_path, extensions):
    """Walk through directories and find audio files with given extensions."""
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.lower().endswith(extensions):
                yield os.path.join(dirpath, filename)


def extract_metadata(file_path):
    """Extract metadata depending on the file type."""
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.flac':
            audio = FLAC(file_path)
        elif ext == '.mp3':
            audio = MP3(file_path)
        elif ext == '.ogg':
            audio = OggVorbis(file_path)
        else:
            logging.warning(f"Unsupported file extension: {file_path}")
            return None
        
        artist = (audio.get('artist') or audio.get('ARTIST') or ['Unknown Artist'])[0]
        title = (audio.get('title') or audio.get('TITLE') or ['Unknown Title'])[0]
        album = (audio.get('album') or audio.get('ALBUM') or ['Unknown Album'])[0]
        year = (audio.get('date') or audio.get('DATE') or [''])[0]
        genre = (audio.get('genre') or audio.get('GENRE') or [''])[0]

        return {
            'artist': artist,
            'title': title,
            'album': album,
            'year': year,
            'genre': genre
        }

    except (ID3NoHeaderError, Exception) as e:
        logging.error(f"Failed to read metadata from {file_path}: {e}")
        return None


def insert_into_db(conn, file_path, metadata):
    """Insert metadata and file info into database."""
    try:
        cursor = conn.cursor()

        query = """
            INSERT INTO songs (filepath, artist, title, album, year, genre)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (
            file_path,
            metadata['artist'],
            metadata['title'],
            metadata['album'],
            metadata['year'],
            metadata['genre']
        ))
        conn.commit()
        logging.info(f"Inserted into DB: {file_path}")
    except mysql.connector.Error as err:
        logging.error(f"Failed to insert {file_path}: {err}")
        logging.error(metadata)
    finally:
        cursor.close()


def main():
    parser = argparse.ArgumentParser(description="Import audio files into MySQL database.")
    parser.add_argument('directory', help="Root directory to scan for audio files")
    parser.add_argument('--db-host', default="localhost", help="Database host")
    parser.add_argument('--db-user', default="root", help="Database user")
    parser.add_argument('--db-password', default="root", help="Database password")
    parser.add_argument('--db-name', default="music", help="Database name")

    args = parser.parse_args()

    conn = connect_db(args.db_host, args.db_user, args.db_password, args.db_name)

    try:
        for file_path in find_audio_files(args.directory, ('.mp3', '.flac', '.ogg')):
            metadata = extract_metadata(file_path)
            if metadata:
                insert_into_db(conn, file_path, metadata)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
