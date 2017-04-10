# Music Library Scripts
These aren't pretty, but they work and perhaps they may give you some ideas (and Pull Requests welcome!)

## Installation

### Prerequisistes
*This list is likely not complete*
```
pacaur -S flac libid3 mysql audacious
```

### Create music database
```
mysql < init.sql
```

#### Initialize the database
*This needs to be cleaned up...*
```
for directory in `ls -d /imagine/flac/jon/*/*`; do
  echo "# $directory"
  musicdir "$directory"
done
```

### Install files
```
cp showoftheday musicdir ~/bin
ln -s ~/bin/showoftheday ~/bin/deadoftheday
```

#### Edit showoftheday
I currently samba mount my music dir to my workstation when I'm home, and the path (`MUSICDIR`) is hardwared.

### To run
* Start `audacious`
* Run `showoftheday` to see all shows from this day in history
* Run `deadoftheday` to restrict the listing to `The_Grateful_Dead`
* Run `showoftheday play` to send the show listings to `audacious`

## Plans for the future
* Update `musicdir` to walk the music folder and update entries when added/deleted
* Enable multiple music folders (Jon's and personal folders if you have them)
* Stream `showoftheday` to an Android (or even securely to my laptop when not at home)
