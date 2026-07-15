---

## name: music-library project assistant
description: >
  Teaches an AI coding assistant how to work effectively on the music-library
  project: a self-hosted FLAC concert-recording index with a MySQL/Docker
  server component (musicdir_index.py) and an interactive CLI
  (showoftheday.py). Use this skill whenever editing server/musicdir_index.py,
  server/init.sql, client/showoftheday.py, server/docker-compose.yml, or
  INSTALL.md; when debugging indexing, playlist generation, or VLC/Music.app
  integration; or when the user mentions shows, tracks, bands, mtimes, or the
  dead.txt filter.

---

# Project Context

Self-hosted music library for a large FLAC soundboard collection on an XUbuntu
Linux server, accessed from macOS. The server indexes files into MySQL; the Mac
CLI queries that DB and launches a local player.

Two distinct "dates" exist in the system:
- **Show date** — the `yyyy-mm-dd` directory name (when the concert happened).
- **Track mtime** — Unix integer timestamp of the `.flac` file on disk (used
  for incremental indexing and `--recent` queries).

# Repository Map

```
music-library/
├── server/
│   ├── docker-compose.yml      # MySQL 8.4 container (name: music_library_db)
│   ├── init.sql                # Schema + idempotent migrations; auto-applied on first start
│   └── musicdir_index.py       # Indexer: walks /imagine/flac → upserts MySQL
└── client/
    └── showoftheday.py         # Interactive CLI → M3U → player
    └── dead.txt                # Optional band filter list (one per line)
```

Both Python scripts use PEP 723 inline metadata (`# /// script`) and are run
with `uv run`.

# Development Workflow

## Running the indexer (server, XUbuntu)

```bash
# Full rescan (required after schema changes):
MUSIC_DB_PASSWORD=mypassword \
  uv run musicdir_index.py --root /imagine/flac --full

# Incremental (nightly cron):
MUSIC_DB_PASSWORD=mypassword \
  uv run musicdir_index.py --root /imagine/flac
```

Cron entry uses the full path to `uv`:
```
0 2 * * * MUSIC_DB_PASSWORD=mypassword \
  /home/youruser/.local/bin/uv run /home/youruser/music-library/server/musicdir_index.py \
  --root /imagine/flac >> /var/log/musicdir_index.log 2>&1
```

## Running the client

```bash
uv run showoftheday.py                        # today's MM-DD
uv run showoftheday.py --date 07-04
uv run showoftheday.py --recent 7
uv run showoftheday.py --dead                 # filter by dead.txt
uv run showoftheday.py --date 07-04 --print   # M3U to stdout
```

## DB container management

```bash
cd server
docker compose up -d          # start
docker compose down -v        # wipe all data (forces schema re-init)

# Ad-hoc SQL:
docker exec -i music_library_db mysql -u music -pmusicpass music -e "SELECT ..."
```

# Implementation Conventions

## File layout expected by indexer

```
/imagine/flac/
  Band_Name/
    yyyy-mm-dd[_extra]/
      ##-Song_Name.flac          # standard
      yyyy-mm-dd.t##.Song.flac   # extended prefix (e.g. Iggy_Pop, Kathleen_Edwards)
      yyyy-mm-ddtNN.flac         # date-only extended prefix (no title)
```

- `_DATE_RE` accepts `yyyy-mm-dd` followed by any word characters.
- `_TRACK_EXT_RE` is tried before `_TRACK_RE`; both are defined at module top.
- Band directory names use underscores; the indexer converts them to spaces for
  the `band` DB column (`band_dir.name.replace("_", " ")`).

## Mtime handling — CRITICAL

`file_mtime` in the DB is **`INT UNSIGNED`** (Unix seconds since epoch), **not
DATETIME**. This was an intentional design decision to avoid MySQL DATETIME(0)
rounding-vs-truncation mismatches that caused perpetual re-indexing.

- **Indexer**: `file_mtime_unix(path)` = `round(path.stat().st_mtime)` → `int`.
- **Client `--recent` queries**: compare against `UNIX_TIMESTAMP() - (%s * 86400)`, not `NOW() - INTERVAL`.
- Never store or compare `file_mtime` as a Python `datetime`.

## Incremental indexing fast-path

Before calling `upsert_show` or any track DB operation, `scan_library` checks
whether every FLAC file in a show directory has an unchanged mtime in
`track_mtime_cache`. If all match, the entire show is skipped (no DB calls, no
logging). This makes nightly runs silent when nothing has changed.

On a fully up-to-date library the only log output is the final summary line:
```
Done. Shows upserted: 0  |  Tracks upserted: 0  |  Tracks skipped (unchanged): N
```

## SQL conventions

- `show_date` column is `DATE`; use `MONTH(show_date)` / `DAY(show_date)` for
  MM-DD queries.
- `CAST(show_date AS CHAR)` returns `yyyy-mm-dd` string reliably (avoids
  `DATE_FORMAT` `%%` escaping bugs with mysql-connector-python).
- `file_mtime` comparisons use `UNIX_TIMESTAMP()` arithmetic (integer math).
- Dynamic `IN (...)` clauses: build `", ".join(["%s"] * len(bands))` and pass
  bands as extra tuple elements — never use f-string interpolation for values.

## Client data model

`Show` has 6 fields: `show_id, band, show_date, dir_path, file_count, album`.
`Track` has 4 fields: `track_id, track_num, title, file_path`.

All show queries include `COALESCE(MIN(t.album), '') AS album` so the `Show`
namedtuple always has a 6th field. The sentinel "all shows" value is
`Show(-1, "", "", "", 0, "")`.

## Player integration

- **Default / Swinsian / IINA**: write temp `.m3u`, `open -a PlayerApp file.m3u`.
- **VLC**: detect by `Path(player).stem.lower() == "vlc"`, call
  `VLC.app/Contents/MacOS/VLC` binary directly after `pkill -x VLC` + 0.3 s
  sleep. VLC's stdout/stderr are suppressed with `DEVNULL`. Do NOT use
  `--one-instance` (broken on macOS) or `--no-playlist-enqueue` (not
  recognised by VLC 3.x).
- **Music.app**: Apple Events `add`/`duplicate` are broken on managed macOS
  devices. Current approach: write `{tmpdir}/FlacLibraryList.m3u`, open with
  `open -a /System/Applications/Music.app`. This creates a playlist named
  after the file stem. `--save` skips the AppleScript pre-delete step.

## Band filter (`--dead`)

`dead.txt` lives next to `showoftheday.py`, one band name per line (underscores
OK). Names are `.replace("_", " ")` to match DB values. Default if file absent:
`["The Grateful Dead"]`. Applied as `AND band IN (...)` in all show/track
queries.

# Schema Overview

| Column | Table | Type | Notes |
|---|---|---|---|
| `shows.show_date` | shows | DATE | Parsed from `yyyy-mm-dd` dir name |
| `shows.dir_path` | shows | VARCHAR | Relative: `Band/yyyy-mm-dd` — unique key |
| `tracks.file_path` | tracks | VARCHAR | Relative: `Band/yyyy-mm-dd/file.flac` — unique key |
| `tracks.file_mtime` | tracks | INT UNSIGNED | Unix timestamp (seconds) |
| `tracks.track_num` | tracks | TINYINT UNSIGNED | Nullable; ≤ 255 |
| `tracks.album` | tracks | VARCHAR(512) | From Vorbis `ALBUM` tag via mutagen |

`init.sql` contains a migration guard:
```sql
ALTER TABLE tracks ADD COLUMN IF NOT EXISTS album VARCHAR(512) DEFAULT NULL AFTER title;
```
Add similar guards for any future schema changes so `init.sql` remains
idempotent against existing databases.

# Common Pitfalls

## Schema migrations on existing containers

`init.sql` `CREATE TABLE IF NOT EXISTS` does **not** alter existing tables.
Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` guards for additive changes.
For destructive changes (column type changes), the safest path is:
`docker compose down -v && docker compose up -d` then `--full` rescan.

## `file_mtime` type mismatch

If `file_mtime` is compared against `NOW()` or stored as a Python `datetime`,
the `--recent` filter silently returns nothing and incremental indexing
re-indexes the same tracks every run. Always use Unix integers end-to-end.

## Perpetual re-indexing

If the same tracks are upserted on every incremental run, check:
1. Is `file_mtime` stored as INT UNSIGNED (not DATETIME)?
2. Is `file_mtime_unix()` using `round()` (not `int()` or `.replace(microsecond=0)`)?
3. Was `--full` run after the schema migration?

## Track number overflow

`track_num` is `TINYINT UNSIGNED` (max 255). Track filenames with non-standard
date prefixes (e.g. `1991-07-12.t03.flac`) can cause the year to be parsed as
the track number. `_TRACK_EXT_RE` must be tried before `_TRACK_RE` to handle
these. If only the standard regex matches, `1991` overflows TINYINT.

## `DATE_FORMAT` and `%%` escaping

`DATE_FORMAT(col, '%%Y-%%m-%%d')` with mysql-connector-python sends `%%Y` to
MySQL, which outputs the literal string `%Y-%m-%d`. Use `CAST(col AS CHAR)`
instead for reliable `yyyy-mm-dd` string output.

## `choose_show` sentinel

The "all shows" sentinel is `Show(-1, "", "", "", 0, "")` — six fields. If the
`Show` namedtuple gains or loses fields, update this sentinel too.

## VLC `--one-instance`

`--one-instance` uses a session socket that is unavailable when the subprocess
is started with `start_new_session=True`. It was tested and confirmed broken.
Use `pkill -x VLC` + fresh start instead.

## Music.app on managed macOS

Apple Events `add` and `duplicate` are silently ignored (not an error) on
managed devices. The M3U file-open approach (`open -a Music.app file.m3u`) is
the only reliable method found.

# Security and Operational Constraints

- DB credentials are passed via environment variables; never hardcode them.
- MySQL port is bound to `127.0.0.1` only in `docker-compose.yml`; access from
  Mac is via SSH tunnel (`LocalForward 3306 127.0.0.1:3306`).
- The Samba mount is read-only from the client's perspective; the indexer reads
  files but never writes to `/imagine/flac`.
- `mutagen` reads FLAC metadata; exceptions are caught and logged as warnings
  (non-fatal).

# Change Checklist

Before committing changes to `musicdir_index.py`:
- [ ] `file_mtime` stored and compared as `int` (Unix seconds)
- [ ] Track filename regexes: `_TRACK_EXT_RE` tried before `_TRACK_RE`
- [ ] Fast-path still skips unchanged shows (no DB calls when mtime matches)
- [ ] Summary log line still emitted at end of run

Before committing changes to `showoftheday.py`:
- [ ] `--recent` queries use `UNIX_TIMESTAMP() - (%s * 86400)` not `NOW() - INTERVAL`
- [ ] Show queries include the `album` column (6th field in `Show`)
- [ ] VLC path: `pkill` + fresh binary launch, not `open -a` or `--one-instance`
- [ ] Dynamic SQL `IN` clauses use parameterised placeholders, not f-string values

Before schema changes to `init.sql`:
- [ ] Additive changes use `ADD COLUMN IF NOT EXISTS`
- [ ] Destructive type changes documented with required migration command
- [ ] `--full` rescan required note added to commit message

# Source of Truth

- **Current schema**: `server/init.sql` (authoritative; README may lag)
- **Filename parsing rules**: `parse_track_filename()` in `musicdir_index.py`
- **CLI flags and defaults**: `parse_args()` in `showoftheday.py`
- **VLC integration behaviour**: `open_in_player()` in `showoftheday.py`
- **Music.app integration**: `load_into_music_app()` in `showoftheday.py`
