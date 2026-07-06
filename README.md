# music-library

A self-hosted concert recording index for FLAC soundboards on a Linux server,
queryable from a Mac CLI.

```
music-library/
├── server/
│   ├── docker-compose.yml   # MySQL 8 container
│   ├── init.sql             # Schema (auto-applied on first start)
│   └── musicdir_index.py    # Server-side indexer / nightly cron job
└── client/
    └── showoftheday.py      # macOS CLI: query by date or recency → M3U
```

---

## 1 · Server setup (XUbuntu)

### 1a. Install Docker

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # log out and back in
```

### 1b. Start the MySQL container

```bash
cd music-library/server

# Optional: set stronger passwords
export MYSQL_ROOT_PASSWORD=supersecret
export MYSQL_PASSWORD=mypassword

docker compose up -d
# MySQL is now reachable at 127.0.0.1:3306 on the server.
```

The `init.sql` schema is applied automatically on first start.

### 1c. Install Python dependencies (server)

```bash
uv pip install mysql-connector-python
```

### 1d. Run the initial full index

```bash
cd music-library/server

MUSIC_DB_PASSWORD=mypassword \
uv run musicdir_index.py --root /imagine/flac --full --verbose
```

This walk takes a minute or two for large libraries (tens of thousands of files).
Subsequent runs are incremental – only new or changed files are touched.

### 1e. Schedule nightly incremental updates

```bash
# Open crontab
crontab -e

# Add (runs at 02:00 every night):
0 2 * * * MUSIC_DB_PASSWORD=mypassword \
  /usr/bin/python3 /home/youruser/music-library/server/musicdir_index.py \
  --root /imagine/flac >> /var/log/musicdir_index.log 2>&1
```

---

## 2 · macOS client setup

### 2a. Mount the Samba share

In Finder: **Go → Connect to Server** → `smb://<server-ip>/imagine`
(or add it to Login Items so it mounts on login.)

The default mount point is `/Volumes/imagine`.

### 2b. Open MySQL port via SSH tunnel (recommended)

Rather than exposing port 3306 to the LAN, use an SSH tunnel on your Mac:

```bash
# Add to ~/.ssh/config on your Mac:
Host music-server
    HostName <server-ip>
    User     <your-linux-user>
    LocalForward 3306 127.0.0.1:3306

# Then connect once:
ssh -fN music-server
```

Now `127.0.0.1:3306` on your Mac connects to the server's MySQL.

Alternatively, change `127.0.0.1:3306:3306` in `docker-compose.yml` to
`0.0.0.0:3306:3306` and open port 3306 in your firewall for LAN-only access.

### 2c. Install Python dependencies (Mac)

```bash
uv pip install mysql-connector-python
```

### 2d. Install a music player

**Swinsian** (recommended – $34.95, 30-day free trial)
<https://swinsian.com>

FLAC-native, M3U import, smart playlists, Apple Silicon. When the script opens
an M3U file, Swinsian loads it as a playlist automatically.

**Free alternatives:** IINA, VLC (both open M3U playlists fine).

---

## 3 · Using the CLI

```bash
cd music-library/client

# Shows performed on today's date in previous years:
uv run showoftheday.py

# Shows on June 13 in any year – pick one interactively:
uv run showoftheday.py --date 06-13

# Shows added in the last 7 days:
uv run showoftheday.py --recent 7

# Recently added, show picker (default); flat track list with --all:
uv run showoftheday.py --recent 7 --all

# Filter to bands listed in dead.txt (defaults to Grateful Dead):
uv run showoftheday.py --dead
uv run showoftheday.py --dead --date 07-04
uv run showoftheday.py --dead --recent 30

# Use a different mount point or player:
uv run showoftheday.py --date 06-13 \
    --mount /Volumes/music \
    --player /Applications/VLC.app

# Just print the M3U to stdout (pipe it, redirect it, etc.):
uv run showoftheday.py --date 06-13 --print
```

### Environment variables

Set these in your shell profile (`~/.zshrc` or `~/.bash_profile`) to avoid
repeating flags:

```bash
export MUSIC_DB_HOST=127.0.0.1    # or server IP if not using SSH tunnel
export MUSIC_DB_PORT=3306
export MUSIC_DB_USER=music
export MUSIC_DB_PASSWORD=mypassword
export MUSIC_DB_NAME=music
export MUSIC_MOUNT=/Volumes/imagine
export MUSIC_PLAYER="/Applications/Swinsian.app"
```

---

## 4 · File layout assumed

```
/imagine/flac/
  Grateful_Dead/
    1977-05-08/
      01-Bertha.flac
      02-Good_Lovin.flac
      ...
  Phish/
    1997-11-17/
      01-Wolfman_s_Brother.flac
      ...
```

- Band directories may use underscores or spaces (both work).
- Date directories must be `yyyy-mm-dd`.
- Track files must end in `.flac`; the leading `##` and `##-` prefix is
  optional but encouraged for ordering.

---

## 5 · Schema overview

| Table    | Purpose                                       |
|----------|-----------------------------------------------|
| `shows`  | One row per `Band/yyyy-mm-dd` directory       |
| `tracks` | One row per `.flac` file                      |
| `v_tracks` | Convenience view joining both tables        |

Useful ad-hoc queries:

```sql
-- All Grateful Dead shows in May:
SELECT band, show_date, dir_path
FROM shows
WHERE band = 'Grateful Dead' AND MONTH(show_date) = 5;

-- Tracks added this week:
SELECT file_path, file_mtime
FROM tracks
WHERE updated_at >= NOW() - INTERVAL 7 DAY
ORDER BY updated_at DESC;
```
