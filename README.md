# Music Library Scripts
These aren't pretty, but they work and perhaps they may give you some ideas (and Pull Requests welcome!)

## Installation

### Prerequisistes
*This list is likely not complete*
```
pacaur -S flac libid3 mysql audacious
```

### Install files
```
cd ~/workspace
git clone git@github.com:openprivacy/music-library.git .
ln -s ~/workspace/music-library/musicdir ~/bin
ln -s ~/workspace/music-library/showoftheday ~/bin
ln -s ~/bin/showoftheday ~/bin/deadoftheday
```

### Create music database
```
mysql < init.sql
```

#### Initialize the database
*This needs to be cleaned up...*
```
export FLACDIR='/imagine/music/flac'
find $FLACDIR -type d -regex ".*/[12X][90X][0-9X][0-9X]-[01X][0-9X]-[0123X][0-9X].?" -exec musicdir {} \;
```

#### Configure showoftheday
I samba mount my music directory to my workstation. `MUSICDIR` defaults to `/imagine/music` and will be mounted if not available. You can skip the mount operation by testing for an already mounted partition, e.g.:
```
export MOUNTDIR=/boot
showoftheday
```

### To run
* Run `showoftheday` to see all shows from this day in history
* Run `showoftheday 12-31` to see all New Years Eve shows
* Run `deadoftheday` to restrict the listing to `The_Grateful_Dead`
* Start `audacious`
* Run `showoftheday play` to send the show listings to `audacious`

## Plans for the future
* Update `musicdir` to:
  * walk the music folder and update entries when added/deleted
  * suck in all directories (not just dates) and comments, too
* Stream `showoftheday` to an Android (or even securely to my laptop when not at home)

## License

GNU General Public License v3.0 or later.

SPDX-License-Identifier: `GPL-3.0-or-later`
