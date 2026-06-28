-- init.sql  –  Music library schema
-- Applied automatically by MySQL on first container start.
-- Re-running this file is safe: every statement uses IF NOT EXISTS / OR REPLACE.

CREATE DATABASE IF NOT EXISTS music
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE music;

-- ---------------------------------------------------------------------------
-- shows
-- One row per concert recording directory (Band_Name/yyyy-mm-dd).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shows (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    band        VARCHAR(255)  NOT NULL,
    show_date   DATE          NOT NULL,       -- parsed from yyyy-mm-dd folder
    dir_path    VARCHAR(1024) NOT NULL,        -- relative path: Band/yyyy-mm-dd
    file_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    added_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_show_dir (dir_path(512)),
    INDEX idx_show_date  (show_date),
    INDEX idx_month_day  ((MONTH(show_date)), (DAY(show_date))),
    INDEX idx_band       (band(100))
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- tracks
-- One row per .flac file.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tracks (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    show_id     INT UNSIGNED  NOT NULL,
    file_path   VARCHAR(1024) NOT NULL,        -- relative: Band/yyyy-mm-dd/##-Song.flac
    track_num   TINYINT UNSIGNED,              -- leading ## parsed from filename
    title       VARCHAR(512)  NOT NULL,        -- Song_Name portion, underscores replaced
    file_mtime  DATETIME      NOT NULL,        -- filesystem modification time
    added_at    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                              ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_track_path (file_path(512)),
    INDEX idx_show   (show_id),
    INDEX idx_mtime  (file_mtime),

    CONSTRAINT fk_track_show
        FOREIGN KEY (show_id) REFERENCES shows (id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Convenience view: full denormalised track listing
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_tracks AS
SELECT
    t.id            AS track_id,
    s.band,
    s.show_date,
    DATE_FORMAT(s.show_date, '%m-%d')   AS month_day,
    YEAR(s.show_date)                   AS show_year,
    t.track_num,
    t.title,
    t.file_path,
    t.file_mtime,
    t.updated_at    AS track_updated_at
FROM tracks t
JOIN shows  s ON s.id = t.show_id;
