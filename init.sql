--	Generate an initial music player database.

DROP DATABASE IF EXISTS music;
CREATE DATABASE music;
USE music;

CREATE TABLE valuet (
  id         SERIAL       NOT NULL,
  valuet     VARCHAR(255) NOT NULL,
UNIQUE INDEX(valuet(160))
);

CREATE INDEX value_id_index ON valuet(id);

CREATE TABLE album (
  id         SERIAL          NOT NULL,                  -- unique identifier
  album      BIGINT UNSIGNED NOT NULL,                  -- value table index of name
  artist     BIGINT UNSIGNED NOT NULL,                  -- value table index of "main" artist name
  single     BOOL            NOT NULL DEFAULT FALSE,    -- true if album is a collection of singles
  directory  TEXT            NOT NULL                   -- filesystem directory containing track files
);

CREATE TABLE aa (
  album      BIGINT UNSIGNED NOT NULL,                  -- unique album identifier
  artist     BIGINT UNSIGNED NOT NULL                   -- unique artist identifier
);

CREATE TABLE track (
  id         BIGINT UNSIGNED NOT NULL,                  -- unique album identifier that matches the one in the album table
  number     INT             NOT NULL DEFAULT 0,        -- track number
  seconds    INT             NOT NULL,                  -- play time in seconds
  file       TEXT            NOT NULL,                  -- name of track file
  artist     BIGINT UNSIGNED NOT NULL,                  -- value table index of artist
  title      BIGINT UNSIGNED NOT NULL,                  -- value table index of title
  intro      TEXT            NOT NULL,                  -- intro flags
  outro      TEXT            NOT NULL,                  -- outro flags
  setname    BIGINT UNSIGNED NOT NULL,                  -- value table index of set label
  comments   TEXT            NOT NULL                   -- general comments
);

DELIMITER |

CREATE PROCEDURE album_id(IN d TEXT, IN a TEXT, IN r TEXT, IN s BOOL, OUT aid INT UNSIGNED)
  BEGIN
    DECLARE  n  BIGINT UNSIGNED;
    DECLARE  t  BIGINT UNSIGNED;

    CALL value_id(a, @n);                               -- get a unique identifier for the album name
    CALL value_id(r, @t);                               -- get a unique identifier for the "main" artist name

    SELECT id INTO aid FROM album WHERE directory=d;    -- find out if the album already exists

    IF aid IS NOT NULL THEN                             -- the album exists
      DELETE FROM track WHERE id=aid;                   -- delete any existing tracks
      UPDATE album SET album=@n, artist=@t, single=s, directory=d WHERE id=aid;  -- modify the album information
    ELSE                                                -- the album does not exist
      INSERT INTO album SET album=@n, artist=@t, single=s, directory=d;          -- create a new album entry
      -- SELECT LAST_INSERT_ID() INTO aid FROM album;   -- fetch the id for the new album
      SELECT id INTO aid FROM album where directory=d;  -- fetch the id for the new album
    END IF;
  END;
|

CREATE PROCEDURE delete_album(IN d TEXT)
  BEGIN
    DECLARE  aid  BIGINT UNSIGNED;

    SELECT id INTO aid FROM album WHERE directory=d;

    IF aid IS NOT NULL THEN
      DELETE FROM aa WHERE album=aid;
      DELETE FROM track WHERE id=aid;
      DELETE FROM album WHERE id=aid;
    END IF;
  END;
|

CREATE PROCEDURE one_track(
  IN  ai BIGINT UNSIGNED,
  IN  tn INT,
  IN  sc INT,
  IN  fl TEXT,
  IN  ar TEXT,
  IN  ti TEXT,
  IN  it TEXT,
  IN  ot TEXT,
  IN  st TEXT,
  IN  co TEXT
 )
  BEGIN
    CALL value_id(ar, @aid);                -- get a unique identifier for the track artist
    CALL value_id(ti, @tid);                -- get a unique identifier for the track title
    CALL value_id(st, @sid);                -- get a unique identifier for the set list

    INSERT INTO track
     SET id=ai, number=tn, seconds=sc, file=fl, artist=@aid, title=@tid, intro=it, outro=ot, setname=@sid, comments=co;
  END;
|

CREATE PROCEDURE value_id(IN v TEXT, OUT vid INT UNSIGNED)
  BEGIN
    SELECT id INTO vid FROM valuet WHERE valuet = v;   -- get any existing identifier for the value

    IF vid IS NULL THEN                                -- looks like there wasn't one
      INSERT INTO valuet SET valuet = v;               -- make a new value table entry
      -- SELECT LAST_INSERT_ID() INTO vid FROM value;  -- grab the identifier for the new entry
      SELECT id INTO vid FROM valuet where valuet = v; -- grab the identifier for the new entry
    END IF;
  END;
|

DELIMITER ;
