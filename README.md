# music-library

A self-hosted concert recording index for FLAC soundboards on a Linux server,
queryable from a Mac or Linux CLI.

```
music-library/
├── server/
│   ├── docker-compose.yml   # MySQL 8 container
│   ├── init.sql             # Schema (auto-applied on first start)
│   └── musicdir_index.py    # Server-side indexer / nightly cron job
└── client/
    └── showoftheday.py      # CLI: query by date or recency → M3U
```

---

For installation instructions, see [INSTALL.md](INSTALL.md)

---

## music-library · Using the CLI

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
