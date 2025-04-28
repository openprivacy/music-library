# Music Library Scripts
These aren't pretty, but they work and perhaps they may give you some ideas (and Pull Requests welcome!)

## Installation

### Install files
```
cd ~/workspace
git clone git@github.com:openprivacy/music-library.git .
ln -s ~/workspace/music-library/showoftheday.py ~/bin/showoftheday
ln -s ~/bin/showoftheday ~/bin/deadoftheday
```

### Create music database
```
mysql < init.sql
```

#### Initialize the database

```
uv run musicdir.py /imagine/flac
```

#### Configure showoftheday
I samba mount my music directory to my workstation. `MUSICDIR` defaults to `/imagine/flac` and will be mounted if not available. You can skip the mount operation by testing for an already mounted partition, e.g.:
```
export MOUNTDIR=/boot
showoftheday
```

### To run
* Run `showoftheday` to see all shows from this day in history
* Run `showoftheday 12-31` to see all New Years Eve shows
* Run `deadoftheday` to restrict the listing to `The_Grateful_Dead`
* Run `showoftheday play` to send the show listings to `rhythmbox`

## Plans for the future
* Update `musicdir` to:
  * walk the music folder and update entries when added/deleted
  * suck in all directories (not just dates) and comments, too
* Stream `showoftheday` to an Android (or even securely to my laptop when not at home)

# Initialize the database
```
docker build -t music-mysql .
FLACDIR=/usb/distrib/jon
docker run -d -p 3306:3306 --name mysql-container -v $FLACDIR:/flac music-mysql

docker run --name music-mysql -e MYSQL_ROOT_PASSWORD=root -d mysql:latest

docker run -it --network some-network --rm mysql mysql -music-mysql -uroot -p

```

## License

GNU General Public License v3.0 or later.

SPDX-License-Identifier: `GPL-3.0-or-later`
